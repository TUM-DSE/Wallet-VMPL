#define _GNU_SOURCE

#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <zygote.h>
#include <trustlet.h>
#include <monitor.h>
#include <time.h>
#include <stdint.h>
#include <sys/time.h>
#include <pthread.h>
#include <sched.h>
#include <unistd.h>
#include <stdio.h>
#include <errno.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#include <rte_eal.h>
#include <rte_errno.h>
#include <rte_ring.h>
#include <rte_mbuf.h>
#include <rte_ether.h>
#include <rte_ip.h>
#include <rte_tcp.h>
#include <rte_vfio.h>
#include <rte_malloc.h>

// --- per-packet TCP telemetry, gated: -DIPERF_PROF (e.g. via EXTRA_CFLAGS).
// ~100-200 cycles per TCP packet on the driver core; prints/dumps are
// event-driven. Compiled out of benchmark builds. ---------------------------
#ifdef IPERF_PROF
// Per-direction TCP packet counters plus an ONLINE desync detector for the
// intermittent "server RSTs mid-transfer with zero drops everywhere" failure
// (3e501ca's seq-desync). The former TIMING-mode trace (printf+fflush for the
// first 4000 packets) sat in the driver's forwarding hot path and perturbed
// exactly the handshake/slow-start phase it was meant to observe; the per-packet
// path must stay print-free in the steady state. Costs here: one 32B trace-ring
// store + a few compares per TCP packet; prints/dumps only fire on the first
// desync event of a connection (which is already dead at that point).
//
// Detectors (per connection, keyed by the client's ephemeral port, all seq
// arithmetic wraparound-aware via int32_t deltas):
//  - DESYNC: a client data segment whose seq is > 64MB past the last ack the
//    server sent. 64MB >> the 16MB sendbuf cap, so no false positives; fires at
//    the moment the client's TCP state has run away (NOT ~700MB later at the RST).
//  - BOGUS-ACK@NIC: the server acks data the client never sent, as seen at the
//    NIC boundary -- if this fires, the corruption happened server-side/vhost;
//    if instead only the trustlet-side detector (ring_rx_burst) fires, the
//    corruption is in the driver-copy->ring->iomgr->trustlet path; if neither
//    fires but DESYNC does, the client's F-Stack state corrupted internally.
// On the first event the driver dumps the trace ring (last TCPTRACE_N TCP
// headers, both directions, with TSC timestamps) to /tmp/tcptrace.txt.
static uint64_t diag_n_sc = 0, diag_n_cs = 0;
// C->S frame size histogram (per IP total_length): <=1500 / <=4K / <=16K / >16K,
// plus the largest frame seen -- to pinpoint the size threshold above which
// TSO super-frames vanish between driver TX and the iperf server.
static uint64_t diag_cs_sz[4] = {0, 0, 0, 0};
static uint32_t diag_cs_max = 0;
// mbuf chain consistency counters: a chain whose segment data_lens don't sum
// to pkt_len, or whose pkt_len disagrees with the IP total_length, produces a
// TRUNCATED frame that the server's ip_input drops silently ("tooshort") --
// which would explain big TSO frames vanishing while single-seg frames pass.
static uint64_t diag_chain_bad = 0, diag_chain_checked = 0;
static void diag_chain_check(const char *where, struct rte_mbuf *m, uint16_t iplen) {
    uint32_t sum = 0;
    uint16_t nseg = 0;
    for (struct rte_mbuf *s = m; s != NULL; s = s->next) {
        sum += s->data_len;
        nseg++;
    }
    diag_chain_checked++;
    if (sum != m->pkt_len || nseg != m->nb_segs ||
            (uint32_t)iplen + RTE_ETHER_HDR_LEN != m->pkt_len) {
        diag_chain_bad++;
        static int logged = 0;
        if (logged++ < 8) {
            printf("CHAIN-BAD %s: pkt_len=%u sum(data_len)=%u nb_segs=%u walked=%u iplen=%u ol_flags=0x%" PRIx64 " tso_segsz=%u\n",
                   where, m->pkt_len, sum, m->nb_segs, nseg, iplen,
                   (uint64_t)m->ol_flags, m->tso_segsz);
            fflush(stdout);
        }
    }
}

#define TCPTRACE_N (1u << 16) // 64k entries * 24B = 1.5MB ring
struct tcpev {
    uint64_t tsc;
    uint32_t seq, ack;
    uint16_t win, len;
    uint8_t flags, dir; // dir: 1 = S->C, 0 = C->S
};
static struct tcpev tcptrace[TCPTRACE_N];
static uint32_t tcptrace_i = 0;

struct tcpconn {
    uint16_t cli_port;        // network byte order; 0 = free slot
    uint32_t last_srv_ack;    // latest ack seen from server (0 = none yet)
    uint32_t max_cli_seq_end; // highest seq+len the client has sent (0 = none yet)
    uint8_t desync_reported, bogus_reported;
};
static struct tcpconn tcpconns[8];

static void tcptrace_dump(const char *why) {
    static int dumped = 0;
    if (dumped++)
        return;
    FILE *f = fopen("/tmp/tcptrace.txt", "w");
    if (!f)
        return;
    fprintf(f, "# dump reason: %s\n# tsc dir seq ack win flags len\n", why);
    for (uint32_t k = 0; k < TCPTRACE_N; k++) {
        struct tcpev *e = &tcptrace[(tcptrace_i + k) % TCPTRACE_N];
        if (e->tsc == 0)
            continue;
        fprintf(f, "%lu %s %u %u %u 0x%02x %u\n", (unsigned long)e->tsc,
                e->dir ? "S->C" : "C->S", e->seq, e->ack, e->win, e->flags, e->len);
    }
    fclose(f);
    printf("TCPTRACE dumped to /tmp/tcptrace.txt (%s)\n", why);
    fflush(stdout);
}

static void diag_tcp(const char *dir, struct rte_mbuf *m) {
    if (rte_pktmbuf_pkt_len(m) < (int)(sizeof(struct rte_ether_hdr) +
            sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_tcp_hdr)))
        return;
    const struct rte_ether_hdr *eth = rte_pktmbuf_mtod(m, const struct rte_ether_hdr *);
    if (eth->ether_type != rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4))
        return;
    const struct rte_ipv4_hdr *ip = (const struct rte_ipv4_hdr *)(eth + 1);
    if (ip->next_proto_id != IPPROTO_TCP)
        return;
    uint8_t ihl = (ip->version_ihl & 0x0f) * 4;
    const struct rte_tcp_hdr *tcp = (const struct rte_tcp_hdr *)((const uint8_t *)ip + ihl);
    uint8_t doff = ((tcp->data_off & 0xf0) >> 4) * 4;
    int payload = (int)rte_be_to_cpu_16(ip->total_length) - ihl - doff;
    int is_sc = (dir[0] == 'S');
    uint32_t seq = rte_be_to_cpu_32(tcp->sent_seq);
    uint32_t ack = rte_be_to_cpu_32(tcp->recv_ack);

    if (is_sc) {
        diag_n_sc++;
    } else {
        diag_n_cs++;
        uint16_t iplen = rte_be_to_cpu_16(ip->total_length);
        diag_cs_sz[iplen <= 1500 ? 0 : iplen <= 4096 ? 1 : iplen <= 16384 ? 2 : 3]++;
        if (iplen > diag_cs_max)
            diag_cs_max = iplen;
        if (iplen > 1500)
            diag_chain_check("tx-copy", m, iplen);
    }

    // RSTs are rare and terminal: log each (bounded) with the ports, and dump
    // the trace ring so the history leading up to the reset is preserved. An
    // RST seen here S->C came from the server/vhost side; if the trustlet
    // reports processing an RST that never appeared here, the confidential
    // path manufactured/corrupted it.
    if (tcp->tcp_flags & RTE_TCP_RST_FLAG) {
        static int rst_logged = 0;
        if (rst_logged < 8) {
            rst_logged++;
            printf("TCP RST@NIC dir=%s src_port=%u dst_port=%u seq=%u ack=%u flags=0x%02x\n",
                   dir, rte_be_to_cpu_16(tcp->src_port), rte_be_to_cpu_16(tcp->dst_port),
                   seq, ack, tcp->tcp_flags);
            fflush(stdout);
        }
        tcptrace_dump("rst-at-nic");
    }
    // Also preserve the trace at normal test end: the first FIN dumps the full
    // seq/ack/window history of the run (needed to diagnose sender stalls that
    // never trigger the RST/desync events).
    if (tcp->tcp_flags & RTE_TCP_FIN_FLAG)
        tcptrace_dump("fin");

    struct tcpev *e = &tcptrace[tcptrace_i++ % TCPTRACE_N];
    e->tsc = rte_rdtsc();
    e->seq = seq; e->ack = ack;
    e->win = rte_be_to_cpu_16(tcp->rx_win);
    e->len = (uint16_t)(payload < 0 ? 0 : payload);
    e->flags = tcp->tcp_flags;
    e->dir = (uint8_t)is_sc;

    // per-connection tracking, keyed by client ephemeral port
    uint16_t key = is_sc ? tcp->dst_port : tcp->src_port;
    struct tcpconn *c = NULL;
    for (int k = 0; k < 8; k++) {
        if (tcpconns[k].cli_port == key) { c = &tcpconns[k]; break; }
        if (tcpconns[k].cli_port == 0 && !c) c = &tcpconns[k];
    }
    if (!c)
        return;
    if (c->cli_port == 0) {
        if (tcp->tcp_flags & RTE_TCP_RST_FLAG)
            return; // don't resurrect slots for stray RSTs
        c->cli_port = key;
        c->last_srv_ack = 0; c->max_cli_seq_end = 0;
        c->desync_reported = 0; c->bogus_reported = 0;
    }

    if (is_sc) {
        if (tcp->tcp_flags & RTE_TCP_ACK_FLAG) {
            // BOGUS-ACK@NIC: server acks beyond everything the client ever sent
            // (+1448 margin for FIN/edge cases)
            if (!c->bogus_reported && c->max_cli_seq_end != 0 &&
                    (int32_t)(ack - c->max_cli_seq_end) > 1448) {
                c->bogus_reported = 1;
                printf("TCP BOGUS-ACK@NIC cli_port=%u ack=%u max_cli_seq_end=%u delta=%d flags=0x%02x\n",
                       rte_be_to_cpu_16(key), ack, c->max_cli_seq_end,
                       (int32_t)(ack - c->max_cli_seq_end), tcp->tcp_flags);
                fflush(stdout);
                tcptrace_dump("bogus-ack-at-nic");
            }
            c->last_srv_ack = ack;
        }
    } else {
        // DESYNC: client data segment far beyond what the server has acked
        if (!c->desync_reported && payload > 0 && c->last_srv_ack != 0 &&
                (int32_t)(seq - c->last_srv_ack) > (64 << 20)) {
            c->desync_reported = 1;
            printf("TCP DESYNC cli_port=%u seq=%u last_srv_ack=%u delta=%d payload=%d\n",
                   rte_be_to_cpu_16(key), seq, c->last_srv_ack,
                   (int32_t)(seq - c->last_srv_ack), payload);
            fflush(stdout);
            tcptrace_dump("client-seq-desync");
        }
        uint32_t seq_end = seq + (uint32_t)(payload > 0 ? payload : 0);
        if (c->max_cli_seq_end == 0 ||
                (int32_t)(seq_end - c->max_cli_seq_end) > 0)
            c->max_cli_seq_end = seq_end;
    }
}
#else
static inline void diag_tcp(const char *dir, struct rte_mbuf *m) { (void)dir; (void)m; }
static inline void diag_chain_check(const char *w, struct rte_mbuf *m, uint16_t l) { (void)w; (void)m; (void)l; }
#endif /* IPERF_PROF */

#include "../include/cpuid.h"
#include "../example-tests/util.h"
#include "../example-tests/util_run.h"
#include "../example-tests/shm_mempool.h"
#include "cvmio.h"
#include "lib.h"

// like test12, but with real CVM IO

#define DATA_SIZE PACKET_SIZE

#ifndef CHAINING
#define CHAINING 2
#endif

#include "iomgr_seg.h"

#ifndef RUNTIME_S
#define RUNTIME_S 15 // measurement duration in --loadgen mode
#endif

/* static void* DATA_SHARED = NULL; */
static __thread bool use_shm_alloc = false;

#define WITH_SHM_ALLOC(expr) ({ \
    use_shm_alloc = true; \
    __typeof__(expr) _result = (expr); \
    use_shm_alloc = false; \
    _result; \
})


// when statically linking DPDK, we make DPDK use these wrappers via --wrap compile flag
// extern void *__real_rte_zmalloc(const char *type, size_t size, unsigned align);
// void *__wrap_rte_zmalloc(const char *type, size_t size, unsigned align) {
//     if (use_shm_alloc) {
//         struct shm* shm = (struct shm*)DATA_SHARED;
//         if (size == TAILQ_ENTRY_SIZE) {
//             return shm->tailq_entry_buf;
//         }
//         return NULL;
//     } else {
//         return __real_rte_zmalloc(type, size, align);
//     }
//     /* return calloc(1, size); */
// }
//
// extern const struct rte_memzone *__real_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align);
// const struct rte_memzone *__wrap_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align) {
//     if (use_shm_alloc) {
//         printf("rte_memzone_reserve_aligned: name=%s, len=%lu, socket_id=%d, flags=%u, align=%u\n", name, len, socket_id, flags, align);
//         struct rte_memzone *mz = calloc(1, sizeof(struct rte_memzone));
//         mz->len = len;
//         mz->socket_id = socket_id;
//         mz->flags = flags;
//         if (len == RING_BUF_SIZE) {
//             mz->addr = ((struct shm*)DATA_SHARED)->ingress.buf;
//         }
//         /* mz->addr = malloc(len); */
//         if (!mz->addr) {
//             printf("Failed to allocate memory for memzone\n");
//         }
//         return mz;
//     } else {
//         return __real_rte_memzone_reserve_aligned(name, len, socket_id, flags, align);
//     }
// }


// Re-stamp a shared-pool mbuf's buf_iova from a LIVE pagemap read. The VFIO
// map of the pool region (see main) swapped the physical pages behind the
// VAs, so any earlier-derived IOVA is stale; and the trustlet's pool
// re-creation stamps buf_iova from mempool metadata that is RTE_BAD_IOVA for
// a NO_IOVA_CONTIG populate. The NIC transmits these mbufs DIRECTLY (zero
// copy), so buf_iova must be the real post-swap physical address. Also verify
// the object is physically contiguous: the whole pool is one CMA block (one
// map call), so a mismatch means the guest hack split the allocation.
static void shm_fix_iova(struct rte_mempool *mp, void *opaque,
        void *obj, unsigned idx) {
    (void)mp; (void)opaque;
    struct rte_mbuf *m = obj;
    m->buf_iova = rte_mem_virt2phy(m->buf_addr);
    phys_addr_t tail = rte_mem_virt2phy((char *)m->buf_addr + m->buf_len - 1);
    if (m->buf_iova == RTE_BAD_IOVA ||
            tail != m->buf_iova + m->buf_len - 1) {
        static int warned = 0;
        if (warned++ < 4)
            printf("SHM pool: obj %u NOT PHYSICALLY CONTIGUOUS (buf_iova=0x%" PRIx64
                   " tail=0x%" PRIx64 ")\n", idx, (uint64_t)m->buf_iova, (uint64_t)tail);
    }
}

int main(int argc, char *argv[]) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t startup_dpdk = ts.tv_sec * 1000000000ULL + ts.tv_nsec;
    // --loadgen: no NIC; the iomgr trustlet acts as load generator and
    // measures VNFlet 0 (MODE_IOMGR_LOADGEN). Note that all other arguments
    // are ignored (EAL args below are hardcoded).
    bool loadgen = false;
    for (int a = 1; a < argc; a++)
        if (strcmp(argv[a], "--loadgen") == 0)
            loadgen = true;

    // with wallet.Wallet() as w:
    monitor_connect();

    // Initialize DPDK EAL with --no-huge for environments without hugepages.
    // virtio init logs at debug so the negotiated feature set (csum/TSO bits)
    // is visible in the driver log -- needed to verify the offload path.
    char *eal_args[] = {"noiomgr_run", "--no-huge", "-l", "0", "--iova-mode=pa",
                        "--log-level=pmd.net.virtio.init:debug"};
    int eal_argc = sizeof(eal_args) / sizeof(eal_args[0]);
    int ret = rte_eal_init(eal_argc, eal_args);
    if (ret < 0) {
        printf("Failed to initialize EAL: %s\n", rte_strerror(rte_errno));
        return -1;
    }

    // Restore full CPU affinity (EAL restricts it to -l cores)
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    for (int i = 0; i < sysconf(_SC_NPROCESSORS_ONLN); i++)
        CPU_SET(i, &cpuset);
    sched_setaffinity(0, sizeof(cpuset), &cpuset);

    struct rte_mempool *cvmio_pool = NULL;
    uint16_t port = 0;
    if (!loadgen) {
        cvmio_pool = cvmio_init();
        port = rte_eth_find_next(0);

        // DIAG: verify the virtio PMD's TX header memzone IOVA against a LIVE
        // pagemap read. Under --no-huge + the guest's VFIO PTE-replacement hack
        // (hacky_atomic_pool_expand swaps the physical pages backing EAL memory),
        // any IOVA recorded before/independent of the swap is stale. Mempool
        // objects get per-page live IOVAs (single-seg TX works), but hdr_mz->iova
        // feeds the virtio-net header + indirect-table descriptors used ONLY by
        // multi-seg/TSO packets -- if it is stale, the vhost backend reads
        // garbage headers and silently drops exactly those frames.
        const struct rte_memzone *hdr_mz = rte_memzone_lookup("port0_vq1_hdr");
        if (hdr_mz) {
            phys_addr_t live = rte_mem_virt2phy(hdr_mz->addr);
            printf("HDR_MZ: addr=%p iova=0x%" PRIx64 " live_pagemap_pa=0x%" PRIx64 "%s\n",
                   hdr_mz->addr, (uint64_t)hdr_mz->iova, (uint64_t)live,
                   (uint64_t)hdr_mz->iova == (uint64_t)live ? " (MATCH)" : " (STALE!)");
        } else {
            printf("HDR_MZ: port0_vq1_hdr not found\n");
        }
        void *probe = rte_malloc(NULL, 64, 64);
        if (probe) {
            printf("HEAP PROBE: addr=%p malloc_iova=0x%" PRIx64 " live_pagemap_pa=0x%" PRIx64 "\n",
                   probe, (uint64_t)rte_malloc_virt2iova(probe),
                   (uint64_t)rte_mem_virt2phy(probe));
            rte_free(probe);
        }
        fflush(stdout);
    }


    // Ring already initialized. We just cast the shm buffer to a ring.
    // // Initialize DPDK ring
    // // TODO create wrappers to also allocate this ring on shm
    // struct rte_ring *ring = WITH_SHM_ALLOC(rte_ring_create("test_ring", 1024, SOCKET_ID_ANY, RING_F_SP_ENQ | RING_F_SC_DEQ));
    // if (!ring) {
    //     printf("Failed to create ring\n");
    //     return -1;
    // }
    // printf("Ring created: %s, count=%u\n", ring->name, rte_ring_count(ring));

    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t startup_zygote = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

    int input_size = 16;

    int chain_len = CHAINING;
    int chains[] = {CHAINING};
    int chains_len = 1;

    uint64_t iterations = -1;

    // One iomgr core per VNFLETS_PER_IOMGR VNFlets (NUM_IOMGR). loadgen drives only
    // VNFlet 0 directly, so it always uses a single iomgr.
    int num_iomgr = loadgen ? 1 : NUM_IOMGR;

    int zygotes[CHAINING];
    int trustlets[CHAINING];
    int iomgr_zygotes[NUM_IOMGR];
    int iomgr_trustlets[NUM_IOMGR];
    struct threaded_invoke_handle* handles[CHAINING];
    struct threaded_invoke_handle* iomgr_handles[NUM_IOMGR];

    // for i in range(chain_len):
    //     zygotes.append(w.create_zygote("../libpal.so", "test4_manifest", "../libsysdb.so"))
    for (int i = 0; i < chain_len; i++) {
        zygotes[i] = create_zygote("../libpal.so", "iomgr_manifest", "../libsysdb.so");
    }
    for (int k = 0; k < num_iomgr; k++) {
        iomgr_zygotes[k] = create_zygote_privileged("../libpal.so", "iomgr_manifest", "../libsysdb.so");
    }

    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t startup_trustlet = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

    // for i in range(chain_len):
    //     trustlets.append(zygotes[i].create_trustlet("./empty.py"))
    for (int i = 0; i < chain_len; i++) {
        trustlets[i] = create_trustlet(zygotes[i], "./empty.py");
    }
    for (int k = 0; k < num_iomgr; k++) {
        iomgr_trustlets[k] = create_trustlet(iomgr_zygotes[k], "./empty.py");
    }

    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t startup_iomgr_shm = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

    // Allocate shared memory at the same VA the trustlet uses (DATA_SHARED),
    // so pointers within shm (e.g. mbuf buf_addr) are valid in both address spaces.
    void *target_addr = (void *)CHANNEL_ADDR(0);
    struct shm* shared = (struct shm*)mmap(target_addr, SHARED_SIZE,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
        -1, 0);
    if (shared == MAP_FAILED) {
        printf("mmap at %p failed: %s\n", target_addr, strerror(errno));
        return -1;
    }
    if (SHARED_SIZE < sizeof(struct shm)) {
        printf("Shared memory size is too small (is: %d, need: %d)\n", SHARED_SIZE, (int)sizeof(struct shm));
        return -1;
    }
    memset(shared, 0, SHARED_SIZE);
    shared->legacy_buffer.data[0] = 'I';
    shared->keep_running = true;

    // Convert the mbuf-pool region of the channel to host-shared DMA memory
    // BEFORE the monitor maps the channel into the trustlets: the VFIO map
    // makes the guest kernel's hacky_atomic_pool_expand replace these pages
    // with ONE physically-contiguous DECRYPTED CMA block behind the same VAs
    // (SEV-SNP: the vhost backend can only read decrypted pages). The NIC then
    // transmits shm-pool mbufs DIRECTLY -- no linearizing bounce copy.
    // Confidentiality note: packet buffers + mbuf headers (and the trailing
    // pool_priv metadata sharing the region's last pages) become host-visible;
    // by design the payload is TLS-protected above TCP, so this only exposes
    // what the NIC would see anyway. The rings and control fields ahead of
    // pool_buf stay guest-private.
    size_t shm_shared_off = offsetof(struct shm, pool_buf); // page-aligned (util.h)
    size_t shm_shared_len = RTE_ALIGN_CEIL(sizeof(struct shm) - shm_shared_off, 4096);
    if (!loadgen) {
        uint64_t pb = (uint64_t)shared + shm_shared_off;
        if (rte_vfio_container_dma_map(RTE_VFIO_DEFAULT_CONTAINER_FD, pb, pb, shm_shared_len)) {
            printf("Failed to vfio-map shm pool region %p len %zu\n",
                   (void *)pb, shm_shared_len);
            return -1;
        }
        printf("SHM pool region vfio-mapped (host-shared): off=%zu len=%zu\n",
               shm_shared_off, shm_shared_len);
        fflush(stdout);
    }

    // Map the channel into each trustlet. In NIC mode the pool region was just
    // converted to host-shared, and the monitor must know: RMPADJUST on
    // hypervisor-owned pages faults, and their trustlet PTEs need the C-bit
    // CLEAR. Bit 63 of the size flags the range as host-shared (SVSM
    // create_shared_memory host-shared support); the ranges before/after are
    // mapped as regular private channel pages.
    #define SHM_MAP_HOST_SHARED (1ULL << 63)
    for (int i = 0; i < chain_len; i++) {
        bool ok;
        if (loadgen) {
            ok = create_shared_memory(trustlets[i], shared, SHARED_SIZE) != NULL;
        } else {
            ok = create_shared_memory(trustlets[i], shared, shm_shared_off) != NULL &&
                 create_shared_memory(trustlets[i], (char *)shared + shm_shared_off,
                                      shm_shared_len | SHM_MAP_HOST_SHARED) != NULL;
        }
        if (!ok) {
            printf("Failed to create shared memory to trustlet %d\n", i);
            return -1;
        }
    }
    // every iomgr needs CHANNEL_ADDR(0) mapped: it holds the mbuf pool and every
    // iomgr dereferences mbuf headers (for rmpadjust / PTE adjustment).
    for (int k = 0; k < num_iomgr; k++) {
        bool ok;
        if (loadgen) {
            ok = create_shared_memory(iomgr_trustlets[k], shared, SHARED_SIZE) != NULL;
        } else {
            ok = create_shared_memory(iomgr_trustlets[k], shared, shm_shared_off) != NULL &&
                 create_shared_memory(iomgr_trustlets[k], (char *)shared + shm_shared_off,
                                      shm_shared_len | SHM_MAP_HOST_SHARED) != NULL;
        }
        if (!ok) {
            printf("Failed to create shared memory to iomgr %d\n", k);
            return -1;
        }
    }
    printf("Shared memory registered\n");

    // Create mbuf pool backed by shared memory
    printf("create_shm_mbuf_pool(%s, %p)\n", "SHM1_MBUF_POOL", shared);
    struct rte_mempool *pool = create_shm_mbuf_pool("SHM1_MBUF_POOL", shared);
    if (!pool) {
        printf("Failed to create shm mbuf pool\n");
        return -1;
    }

    shared->mbuf_pool = pool;
    printf("Mbuf pool created with %u objects\n", pool->populated_size);

    // allocate second shm
    target_addr = (void *)CHANNEL_ADDR(1);
    struct shm* shared2 = (struct shm*)mmap(target_addr, SHARED_SIZE,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
        -1, 0);
    if (shared2 == MAP_FAILED) {
        printf("mmap at %p failed: %s\n", target_addr, strerror(errno));
        return -1;
    }
    memset(shared2, 0, SHARED_SIZE);
    shared2->legacy_buffer.data[0] = 'I';
    shared2->keep_running = true;
    // CHANNEL_ADDR(1) is the chain exit: only the last iomgr writes packets (and
    // loadgen results) back to the driver through it.
    if (!create_shared_memory(iomgr_trustlets[num_iomgr - 1], shared2, SHARED_SIZE)) {
        printf("Failed to create shared memory\n");
        return -1;
    }

    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t startup_init_trustlets = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

    // We do the following in the first trustlet now, because we are missing the allocator wrappers here that are present in the trustlet. I dont want to add them here, because it would pollute our cvmio external setup maybe?
    // // Create mbuf pool backed by shared memory
    // printf("create_shm_mbuf_pool(%s, %p)\n", "SHM2_MBUF_POOL", shared2);
    // struct rte_mempool *pool2 = create_shm_mbuf_pool("SHM2_MBUF_POOL", shared2);
    // if (!pool2) {
    //     printf("Failed to create shm mbuf pool\n");
    //     return -1;
    // }

    // shared2->mbuf_pool = pool2;
    // printf("Mbuf pool created with %u objects\n", pool2->populated_size);

    // input_data = b"a" * (input_size - 1) + b"\00"
    char input_data[16];
    memset(input_data, 'a', input_size - 1);
    input_data[input_size - 1] = '\0';

    // for t in trustlets:
    //     t.invoke_trustlet(input_data, len(input_data))
    for (int t = 0; t < chain_len; t++) {
        printf("152:invoke_trustlet()\n");
        invoke_trustlet(trustlets[t], input_data, input_size);
    }
    for (int k = 0; k < num_iomgr; k++) {
        invoke_trustlet(iomgr_trustlets[k], input_data, input_size);
    }

    // for i in chains:
    for (int idx = 0; idx < chains_len; idx++) {
        int i = chains[idx];

        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t startup_trustlet_shm = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        // #Create chains
        // Each VNFlet's ring-pair channel is shared with the iomgr that owns its
        // segment (loadgen always uses iomgr 0).
        // for c in range(chained,i - 1):
        //     trustlets[c].create_channel(trustlets[c+1])
        for (int c = 0; c < i; c++) {
            // create_channel(trustlets[c], trustlets[c+1]);
            int owner = loadgen ? 0 : (c / VNFLETS_PER_IOMGR);
            create_channel_at(iomgr_trustlets[owner], trustlets[c], (uint64_t)CHANNEL_ADDR(2+c), SHARED_SIZE);
        }

        // Handoff channels connecting consecutive iomgrs in the pipeline.
        for (int k = 0; k < num_iomgr - 1; k++) {
            create_channel_at(iomgr_trustlets[k], iomgr_trustlets[k+1], (uint64_t)IOMGR_HANDOFF_ADDR(k), SHARED_SIZE);
        }

        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t startup_init_trustlets2 = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        // Configure first-in-chain trustlet
        struct trustlet_configuration config;
        config.mode[0] = MODE_FIRST_NODE;
        config.shm_addr_previous = CHANNEL_ADDR(2);
        config.shm_addr_next = CHANNEL_ADDR(0);
        invoke_trustlet_bin(trustlets[0], &config, sizeof(config), 0);

        // #Setup Trustlets
        // for t in range(i - 1):
        //     trustlets[t].invoke_trustlet(b"a", 0)
        printf("185:invoke_trustlet()\n");
        for (int t = 1; t < i - 1; t++) {
            // Transfer nodes (input->output)
            config.mode[0] = MODE_MIDDLE_NODE;
            config.shm_addr_previous = CHANNEL_ADDR(2+t);
            config.shm_addr_next = CHANNEL_ADDR(0);
            invoke_trustlet_bin(trustlets[t], &config, sizeof(config), 0);
        }
        // trustlets[i - 1].invoke_trustlet(b"s", 0)
        // End node - use shm mode
        // (with chaining == 1, trustlet 0 is both first and last node. It is already
        // configured above; a second config invocation would resume its processing
        // loop on this thread and deadlock.)
        if (i > 1) {
            config.mode[0] = MODE_LAST_NODE;
            config.shm_addr_previous = CHANNEL_ADDR(i+1);
            config.shm_addr_next = CHANNEL_ADDR(0);
            invoke_trustlet_bin(trustlets[i - 1], &config, sizeof(config), 0);
        }

        // Setup IoMgrs. Configure in increasing order so that iomgr k's input
        // channel (a handoff created/pooled by iomgr k-1) is ready before iomgr k
        // reads it.
        for (int k = 0; k < num_iomgr; k++) {
            struct iomgr_config iocfg;
            iocfg.base.mode[0] = loadgen ? MODE_IOMGR_LOADGEN : MODE_IOMGR_NODE;
            // input: driver (iomgr 0) or the previous iomgr's handoff channel
            iocfg.base.shm_addr_previous = (k == 0) ? CHANNEL_ADDR(0) : IOMGR_HANDOFF_ADDR(k - 1);
            // output: driver (last iomgr) or the next iomgr's handoff channel
            iocfg.base.shm_addr_next = (k == num_iomgr - 1) ? CHANNEL_ADDR(1) : IOMGR_HANDOFF_ADDR(k);
            iocfg.seg_start = IOMGR_SEG_START(k);
            iocfg.seg_end = IOMGR_SEG_END(k);
            printf("Configuring iomgr %d: VNFlets [%d, %d), prev=%p, next=%p\n",
                   k, iocfg.seg_start, iocfg.seg_end, iocfg.base.shm_addr_previous, iocfg.base.shm_addr_next);
            invoke_trustlet_bin(iomgr_trustlets[k], &iocfg, sizeof(iocfg), 0);
        }

        // Re-stamp the shared pool's buf_iova values now that (a) the VFIO map
        // swapped the physical pages and (b) the iperf VNFlet's config
        // invocation above re-created the pool (its rte_pktmbuf_init leaves
        // buf_iova invalid for a NO_IOVA_CONTIG populate). Must precede any
        // mbuf reaching the NIC -- the PMD DMAs straight from these buffers.
        if (!loadgen) {
            rte_mempool_obj_iter(pool, shm_fix_iova, NULL);
            printf("SHM pool buf_iova re-stamped for zero-copy TX\n");
            fflush(stdout);
        }

        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t startup_launch_trustlets = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        // start long-running trustlets (each trustlet exactly once; with
        // chaining == 1, trustlet 0 is the single first==last node)
        /* invoke_trustlet(trustlets[1], "s", 0); */
        // Interleave CPU pinning so each iomgr sits on the core right after the
        // VNFlet cores of the segment it serves: v0..v8, iomgr0, v9..v17, iomgr1, ...
        // (the iomgr follows its VNFlets, as in the previous single-iomgr layout).
        int vnflet_core[CHAINING];
        int iomgr_core[NUM_IOMGR];
        {
            int core = 1; // core 0 is reserved for the driver
            for (int k = 0; k < num_iomgr; k++) {
                int seg_lo = loadgen ? 0 : IOMGR_SEG_START(k);
                int seg_hi = loadgen ? i : IOMGR_SEG_END(k);
                for (int t = seg_lo; t < seg_hi; t++)
                    vnflet_core[t] = core++;
                iomgr_core[k] = core++;
            }
        }

        for (int t = 0; t < i; t++) {
            printf("Starting trustlet %d on core %d\n", t, vnflet_core[t]);
            handles[t] = threaded_invoke(trustlets[t], vnflet_core[t], "", 0);
        }
        for (int k = 0; k < num_iomgr; k++) {
            printf("Starting IoMgr %d on core %d\n", k, iomgr_core[k]);
            iomgr_handles[k] = threaded_invoke(iomgr_trustlets[k], iomgr_core[k], "", 0);
        }

        size_t enq_num = 0, num_enqed = 0, deq_num = 0, num_deqed = 0;
        void *enq_objs[BURST_SIZE];
        void *deq_objs[BURST_SIZE];
        struct rte_mbuf *bufs[BURST_SIZE];

        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t startup_data_loop = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        printf("STARTUP name duration_s\n");
        printf("STARTUP dpdk %.6f\n",             (startup_zygote           - startup_dpdk)            / 1e9);
        printf("STARTUP zygote %.6f\n",           (startup_trustlet         - startup_zygote)          / 1e9);
        printf("STARTUP trustlet %.6f\n",         (startup_iomgr_shm        - startup_trustlet)        / 1e9);
        printf("STARTUP iomgr_shm %.6f\n",        (startup_init_trustlets   - startup_iomgr_shm)       / 1e9);
        printf("STARTUP init_trustlets %.6f\n",   (startup_trustlet_shm     - startup_init_trustlets)  / 1e9);
        printf("STARTUP trustlet_shm %.6f\n",     (startup_init_trustlets2  - startup_trustlet_shm)    / 1e9);
        printf("STARTUP init_trustlets2 %.6f\n",  (startup_launch_trustlets - startup_init_trustlets2) / 1e9);
        printf("STARTUP launch_trustlets %.6f\n", (startup_data_loop        - startup_launch_trustlets)/ 1e9);
        printf("STARTUP total %.6f\n",            (startup_data_loop        - startup_dpdk)            / 1e9);
        fflush(stdout);

        // dump SVSM page-count stats before the hot loop starts
        // (requires SVSM built with FEATURE="stat"; trustlets must trigger mem_stat via notify_monitor)
        printf("MEM_STAT pre-hot-loop\n");
        fflush(stdout);
        stat_get();

        printf("Starting %d iterations...\n", iterations);
        // create file /tmp/.dpdk-running to signal that the program is running (for external scripts)
        int fd = open("/tmp/.dpdk-running", O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) {
            printf("Failed to create /tmp/.dpdk-running: %s\n", strerror(errno));
            fflush(stdout);
            return 1;
        }
        close(fd);

        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t start = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        if (loadgen)
            sleep(RUNTIME_S); // the iomgr drives VNFlet 0 internally; we only control the duration

        // DIAG: silent drops here (pool exhausted -> copy NULL, or ring full)
        // collapse the iperf VNFlet transfer; count them and print rarely.
        uint64_t drop_rx_copy = 0, drop_rx_ring = 0, drop_tx_copy = 0, drop_tx_ring = 0;
        uint64_t diag_next = 20000000;
        // for _ in range(iterations):
        for (int iter = 0; iter < iterations && !loadgen; iter++) {
#ifdef IPERF_PROF
            if ((uint64_t)iter >= diag_next) {
                diag_next = (uint64_t)iter + 20000000;
                printf("DRV DIAG: iter=%d drop_rx_copy=%lu drop_rx_ring=%lu drop_tx_copy=%lu drop_tx_ring=%lu tcp_rx=%lu tcp_tx=%lu tx_sz=%lu/%lu/%lu/%lu max=%u c2d_ring=%u pool_avail=%u\n",
                       iter, (unsigned long)drop_rx_copy, (unsigned long)drop_rx_ring,
                       (unsigned long)drop_tx_copy, (unsigned long)drop_tx_ring,
                       (unsigned long)diag_n_sc, (unsigned long)diag_n_cs,
                       (unsigned long)diag_cs_sz[0], (unsigned long)diag_cs_sz[1],
                       (unsigned long)diag_cs_sz[2], (unsigned long)diag_cs_sz[3],
                       diag_cs_max,
                       // standing-queue locator: C->S ring depth at the driver
                       // (full => driver/NIC/backend is the slow stage; empty
                       // => upstream iomgr/vnflet is) and shared-pool avail
                       rte_ring_count(&shared2->ingress.ring),
                       rte_mempool_avail_count(pool));
                fflush(stdout);
            }
#endif /* IPERF_PROF */

            const uint16_t nb_rx = rte_eth_rx_burst(port, 0,
                    bufs, BURST_SIZE); // bufs in cvmio pool

            if (unlikely(nb_rx == 0)) {
                /* rx_err++; */
            } else {
                // Copy received packets into mbufs from the shm pool
                size_t nb_copied = 0;
                for (size_t i = 0; i < nb_rx; i++) {
                    diag_tcp("S->C", bufs[i]); // server->client: watch advertised window
                    enq_objs[nb_copied] = rte_pktmbuf_copy(bufs[i], pool, 0, UINT32_MAX); // TODO not MAX
                    rte_pktmbuf_free(bufs[i]); // return to cvmio_pool
                    if (enq_objs[nb_copied] != NULL)
                        nb_copied++;
                    else
                        drop_rx_copy++; // shared pool exhausted -> RX (ACK) dropped
                }

                if (nb_copied > 0) {
                    enq_num = rte_ring_sp_enqueue_bulk(&shared->ingress.ring, enq_objs, nb_copied, NULL);
                    if (enq_num == 0) {
                        drop_rx_ring += nb_copied; // VNFlet-bound ingress ring full
                        rte_pktmbuf_free_bulk((struct rte_mbuf **)enq_objs, nb_copied); // return to pool
                    }
                    else
                        num_enqed += enq_num;
                }

            }

            // receive empty buffers back and return them to pool
            deq_num = rte_ring_sc_dequeue_burst(&shared->egress.ring, deq_objs, BURST_SIZE, NULL);
            if (deq_num > 0) {
                for (size_t j = 0; j < deq_num; j++) {
                    rte_pktmbuf_free(deq_objs[j]); // return to pool TODO: this is propably also wrong
                }
            }

            // Dequeue processed mbufs
            deq_num = rte_ring_sc_dequeue_burst(&shared2->ingress.ring, deq_objs, BURST_SIZE, NULL);
            if (deq_num > 0) {
                // ZERO-COPY TX: the shm-pool mbufs are host-shared DMA memory
                // with live buf_iova (vfio map + shm_fix_iova above), so hand
                // them to virtio directly. They are single-segment whole TSO
                // frames (33KB data room + tso_max clamp) -> can_push path.
                // The virtio TX vq frees transmitted mbufs only lazily, from
                // inside a LATER tx_burst call; it could absorb the whole
                // shared pool and starve the trustlet (permanent wedge), so
                // force the cleanup whenever the pool runs low.
                if (rte_mempool_avail_count(pool) < SHM_POOL_SIZE / 2)
                    rte_eth_tx_done_cleanup(port, 0, 0);
                size_t nb_tx_ready = 0;
                for (size_t i = 0; i < deq_num; i++) {
                    struct rte_mbuf *src = (struct rte_mbuf *)deq_objs[i];
                    if (src->pkt_len > 1514) // whole TSO frame from the shared rings
                        diag_chain_check("src", src, (uint16_t)(src->pkt_len - RTE_ETHER_HDR_LEN));
                    if (unlikely(src->nb_segs > 1)) {
                        // multi-seg TX is broken on this rig (non-can_push
                        // descriptor path); should not happen with the 33KB
                        // data room + tso_max clamp -- drop VISIBLY if it does
                        rte_pktmbuf_free(src);
                        drop_tx_copy++;
                        continue;
                    }
                    diag_tcp("C->S", src);
                    bufs[nb_tx_ready++] = src;
                }

                if (nb_tx_ready > 0) {
                    const uint16_t nb_tx = rte_eth_tx_burst(port, 0,
                            bufs, nb_tx_ready);
                    // the PMD owns and later frees the accepted mbufs (back to
                    // the shared pool via mbuf->pool = shm_stack ops)
                    if (unlikely(nb_tx < nb_tx_ready)) {
                        uint16_t buf;
                        drop_tx_ring += (nb_tx_ready - nb_tx); // NIC TX ring full
                        for (buf = nb_tx; buf < nb_tx_ready; buf++)
                            rte_pktmbuf_free(bufs[buf]); // back to the shared pool
                    }
                }

                num_deqed += deq_num;

            }
        }

        atomic_store(&shared->keep_running, false); // signal first trustlet to stop
        /* shared->keep_running = false; // signal trustlet to stop */
        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t end = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        for (int t = 0; t < i; t++) {
            if (handles[t] != NULL) {
                char* _res = threaded_join(handles[t]);
                threaded_free(handles[t]);
            }
        }
        // join iomgrs in order: the driver stops iomgr 0 (via CHANNEL_ADDR(0)
        // keep_running), which cascades the stop signal down the pipeline.
        for (int k = 0; k < num_iomgr; k++) {
            char* _res = threaded_join(iomgr_handles[k]);
            threaded_free(iomgr_handles[k]);
        }

        if (loadgen) {
            // written by the iomgr trustlet before it exits (joined above)
            struct loadgen_results *res = &shared2->loadgen_results;
            double pps = res->elapsed_ns ? res->packets / (res->elapsed_ns / 1e9) : 0.0;
            printf("Loadgen measured VNFlet 0: %lu packets in %.3f s\n",
                   res->packets, res->elapsed_ns / 1e9);
            printf("Mpps: %.3f\n", pps / 1e6);

            // result file for pybench/measure_vm.py (write + rename so it appears atomically)
            FILE *f = fopen("/tmp/iomgr_microbenchmark.out.tmp", "w");
            if (!f) {
                printf("Failed to write /tmp/iomgr_microbenchmark.out.tmp: %s\n", strerror(errno));
                return 1;
            }
            fprintf(f, "pps %f\n", pps);
            fprintf(f, "tx_packets %lu\n", res->packets);
            fprintf(f, "rx_packets %lu\n", res->packets);
            fclose(f);
            rename("/tmp/iomgr_microbenchmark.out.tmp", "/tmp/iomgr_microbenchmark.out");
        } else {
            printf("%d iterations took %.3f s\n", iterations, 1.0 * (end - start) / 1e9);
            printf("Mpps: %.3f\n", num_deqed / ((end - start) / 1e9) / 1e6);
            printf("Successfully enqueued %lu objects\n", num_enqed);
            printf("Successfully dequeued %lu objects\n", num_deqed);
        }
    }

    return 0;
}
