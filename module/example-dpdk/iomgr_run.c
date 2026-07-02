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

// DIAG: parse a TCP packet and print (rate-limited) direction/seq/ack/flags/win/
// payload so we can watch the client<->server TCP conversation from the driver's
// NIC vantage -- specifically the server's advertised receive window over time
// (a persist/zero-window deadlock shows win pinning at 0 and never reopening) and
// tiny client persist probes. dir: "S->C" (NIC RX) or "C->S" (NIC TX).
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
    uint16_t iplen = rte_be_to_cpu_16(ip->total_length);
    uint8_t doff = ((tcp->data_off & 0xf0) >> 4) * 4;
    int payload = (int)iplen - ihl - doff;
    // Rate-limit per direction: log the first ~40, then only on zero-window,
    // window reopen, or once per ~200ms; always log tiny (persist) segments.
    static uint64_t n_sc = 0, n_cs = 0, last_sc_ns = 0, last_cs_ns = 0;
    static uint32_t last_sc_win = 0xffffffff;
    int is_sc = (dir[0] == 'S');
    uint16_t win = rte_be_to_cpu_16(tcp->rx_win);
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t now = ts.tv_sec * 1000000000ULL + ts.tv_nsec;
    uint64_t *cnt = is_sc ? &n_sc : &n_cs;
    uint64_t *last = is_sc ? &last_sc_ns : &last_cs_ns;
    (*cnt)++;
    int win_event = is_sc && (win != last_sc_win) && (win == 0 || last_sc_win == 0);
    int small = payload > 0 && payload <= 4; // persist probe
    if (*cnt <= 40 || win_event || small || (now - *last) > 200000000ULL) {
        *last = now;
        if (is_sc) last_sc_win = win;
        printf("TCP %s #%lu seq=%u ack=%u win=%u flags=0x%02x payload=%d%s\n",
               dir, (unsigned long)*cnt, rte_be_to_cpu_32(tcp->sent_seq),
               rte_be_to_cpu_32(tcp->recv_ack), win, tcp->tcp_flags, payload,
               win_event ? (win == 0 ? "  <<ZERO-WINDOW" : "  <<WIN-REOPEN") : "");
        fflush(stdout);
    }
}

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

    // Initialize DPDK EAL with --no-huge for environments without hugepages
    char *eal_args[] = {"noiomgr_run", "--no-huge", "-l", "0", "--iova-mode=pa"};
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
    for (int i = 0; i < chain_len; i++) {
        if (!create_shared_memory(trustlets[i], shared, SHARED_SIZE)) {
            printf("Failed to create shared memory to trustlet %d\n", i);
            return -1;
        }
    }
    // every iomgr needs CHANNEL_ADDR(0) mapped: it holds the mbuf pool and every
    // iomgr dereferences mbuf headers (for rmpadjust / PTE adjustment).
    for (int k = 0; k < num_iomgr; k++) {
        if (!create_shared_memory(iomgr_trustlets[k], shared, SHARED_SIZE)) {
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
            if ((uint64_t)iter >= diag_next) {
                diag_next = (uint64_t)iter + 20000000;
                printf("DRV DIAG: iter=%d drop_rx_copy=%lu drop_rx_ring=%lu drop_tx_copy=%lu drop_tx_ring=%lu\n",
                       iter, (unsigned long)drop_rx_copy, (unsigned long)drop_rx_ring,
                       (unsigned long)drop_tx_copy, (unsigned long)drop_tx_ring);
                fflush(stdout);
            }

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
                size_t nb_copied2 = 0;
                for (size_t i = 0; i < deq_num; i++) {
                    bufs[nb_copied2] = rte_pktmbuf_copy(deq_objs[i], cvmio_pool, 0, UINT32_MAX); // TODO not MAX
                    /* rte_pktmbuf_free(deq_objs[i]); // return to last VNFlet's pool (don't, its not thread safe) */
                    if (bufs[nb_copied2] != NULL)
                        nb_copied2++;
                    else
                        drop_tx_copy++; // cvmio (NIC) pool exhausted -> client TX dropped
                    rte_pktmbuf_free(deq_objs[i]); // return to pool1
                }

                if (nb_copied2 > 0) {
                    for (size_t i = 0; i < nb_copied2; i++)
                        diag_tcp("C->S", bufs[i]); // client->server: spot persist probes
                    const uint16_t nb_tx = rte_eth_tx_burst(port, 0,
                            bufs, nb_copied2);

                    /* Free any unsent packets */
                    if (unlikely(nb_tx < nb_copied2)) {
                        uint16_t buf;
                        drop_tx_ring += (nb_copied2 - nb_tx); // NIC TX ring full
                        for (buf = nb_tx; buf < nb_copied2; buf++)
                            rte_pktmbuf_free(bufs[buf]); // return to cvmio_pool
                    }
                }

                // i think this is not necessary. We the buffers are from pool1, so we must free them ourselves:
                // // return empty buffer to previous (our mempool is not atomic, so we have to pass back atomically)
                // size_t nb_returned = rte_ring_sp_enqueue_bulk(&shared2->egress.ring, (void**)(&(deq_objs[0])), deq_num, NULL);
                // if (nb_returned != deq_num) {
                //     printf("Warning: failed to return %lu buffers to shared2->egress\n", deq_num);
                // }

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
