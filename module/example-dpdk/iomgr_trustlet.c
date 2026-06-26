#include <stdio.h>
#include <sys/io.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include <time.h>

#include <rte_eal.h>
#include <rte_errno.h>
#include <rte_ring.h>
#include <rte_memzone.h>
#include <rte_mbuf.h>

#include "cpuid.c"
#include "../example-tests/util.h"
#include "../example-tests/shm_mempool.h"
#include "workload.h"
#include "ipsec.h"
#include "ids.h"

#define PORT 0xF4
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000
#define DATA_SHARED 0x38000000000

#ifndef DATA_SIZE
#define DATA_SIZE 16
#endif

#ifndef PER_VNFLET_WORKLOAD_NS
#define PER_VNFLET_WORKLOAD_NS 0
#endif

#ifndef CHAINING
#define CHAINING 2
#endif

#ifndef PACKET_SIZE
#define PACKET_SIZE 64
#endif

// number of mbufs the loadgen keeps in flight towards VNFlet 0 (must be < RING_SIZE
// so re-enqueueing into the ingress ring can never fail)
#ifndef LOADGEN_INFLIGHT
#define LOADGEN_INFLIGHT 512
#endif

// #define REAL_WORKLOAD

#define println(...) do { fprintf(stdout, __VA_ARGS__); fflush(stdout); } while(0)
#define READ_ONCE(x) (*(volatile typeof(x) *)&(x))

void hexdump(const void *data, size_t size) {
    for (size_t i = 0; i < size; i++) printf("%02x ", ((unsigned char *)data)[i]);
    println("");
}

static void* next_tailq_buf = NULL;
static void* next_memhdr_buf = NULL;

// when statically linking DPDK, we make DPDK use these wrappers via --wrap compile flag
void *__wrap_rte_zmalloc(const char *type, size_t size, unsigned align) {
    if (size == TAILQ_ENTRY_SIZE) {
        return next_tailq_buf;
    }
    if (size == sizeof(struct rte_mempool_memhdr)) {
        return next_memhdr_buf;
    }
    return NULL;
    /* return calloc(1, size); */
}

static void* next_alloc_buffer = NULL;

const struct rte_memzone *__wrap_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align) {
    println("rte_memzone_reserve_aligned: name=%s, len=%lu, socket_id=%d, flags=%u, align=%u", name, len, socket_id, flags, align);
    struct rte_memzone *mz = calloc(1, sizeof(struct rte_memzone));
    mz->len = len;
    mz->socket_id = socket_id;
    mz->flags = flags;
    if (len == RING_BUF_SIZE || len == POOL_PRIV_SIZE) { // sanity check. These are the only two allocations we are expecting
        mz->addr = next_alloc_buffer;
    }
    /* mz->addr = malloc(len); */
    if (!mz->addr) {
        println("Failed to allocate memory for memzone");
    }
    return mz;
}

// used for struct rte_pktmbuf_pool_private
const struct rte_memzone *__wrap_rte_memzone_reserve(const char *name,
			size_t len, int socket_id,
			unsigned flags) {
	assert(((len + RTE_MEMPOOL_ALIGN_MASK) & (~RTE_MEMPOOL_ALIGN_MASK)) == POOL_PRIV_SIZE);
	return __wrap_rte_memzone_reserve_aligned(name, len, socket_id, flags, -1);
}


// CPU frequency in GHz - used to correct clock_gettime which returns TSC cycles
#define CPU_GHZ 2.0

// Returns monotonic time in nanoseconds
// Note: clock_gettime returns TSC cycles misinterpreted as usec, then converted to nsec
// Effective value is cycles * 1000, so divide by (CPU_GHZ * 1000) to get real nsec
static inline uint64_t clock_monotonic_get(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (ts.tv_sec * 1000000000ULL + ts.tv_nsec) / (CPU_GHZ * 1000);
}

static inline void nop_loop(uint64_t count) {
    for (volatile uint64_t i = 0; i < count; i++) {
        __asm__ volatile("nop");
    }
}

static double nops_per_ns = 1.617; // result of calibrate_nop_delay() on ryan

// Calibrate how many NOPs correspond to 1 ns of wall-clock time.
// Runs an increasing number of NOPs and measures elapsed time with clock_monotonic_get.
// Note: each clock_monotonic_get call takes ~11ms in Gramine/SVSM, so we need
// enough NOPs to dominate that overhead.
void calibrate_nop_delay(void) {
    uint64_t target_ns = 100000000ULL; // 100ms calibration target
    uint64_t nops = 1000000; // start with 1M NOPs

    for (int attempt = 0; attempt < 10; attempt++) {
        uint64_t start = clock_monotonic_get();
        nop_loop(nops);
        uint64_t end = clock_monotonic_get();
        uint64_t elapsed_ns = end - start;

        println("calibrate: %lu NOPs took %lu ns", nops, elapsed_ns);

        if (elapsed_ns > 0) {
            nops_per_ns = (double)nops / (double)elapsed_ns;
            // If elapsed is close enough to target (within 2x), we're done
            if (elapsed_ns >= target_ns / 2 && elapsed_ns <= target_ns * 2) {
                println("calibrated: %.3f NOPs/ns", nops_per_ns);
                return;
            }
            // Scale nops to hit the target
            nops = (uint64_t)((double)nops * (double)target_ns / (double)elapsed_ns);
        } else {
            nops *= 10;
        }
    }
    println("calibrated (fallback): %.3f NOPs/ns", nops_per_ns);
}

// NOP-based delay that avoids expensive clock_gettime calls.
// Must call calibrate_nop_delay() once before using this.
void nop_delay(uint64_t nsecs) {
    if (nsecs == 0) return;
    assert(nops_per_ns > 0 && "nop_delay called before calibration");
    nop_loop((uint64_t)(nsecs * nops_per_ns));
}

uint64_t delayed_ns = 0;
uint64_t delays = 0;

// build our own delay, because gramine's sleep is unimplemented
void delay(uint64_t nsecs) {
    if (nsecs == 0) return;

    uint64_t start = clock_monotonic_get();
    uint64_t end = start + nsecs;
    debug println("delay: start=%lu, end=%lu, waiting for %lu ns", start, end, nsecs);
    while (1) {
        uint64_t now = clock_monotonic_get();
        if (now >= end) {
            delays++;
            delayed_ns += now - start;
            debug println("my delay: done, slept %lu ns", now - start);
            break;
        }
    }
}


// vaddr: guest virtual address of the page to adjust
// rmp_psize: RMP_PG_SIZE_4K
#define RMP_PG_SIZE_4K      0
#define RMPADJUST_VMSA_PAGE_BIT   (1<<(16))

#define VMPL0 0
#define VMPL1 1
#define VMPL2 2
#define VMPL3 3
#define VMPL_MASK_START
#define VMPL_READ (1<<(VMPL_MASK_START+0))
#define VMPL_WRITE (1<<(VMPL_MASK_START+1))
#define VMPL_EXEC_USER (1<<(VMPL_MASK_START+2))
#define VMPL_EXEC_SUPERVISOR (1<<(VMPL_MASK_START+3))
#define VMPL_SSS (1<<(VMPL_MASK_START+4))
// bit 5-7 reserved


static inline int rmpadjust(unsigned long vaddr, bool rmp_psize, unsigned long attrs)
{
	int rc;

	attrs &= !RMPADJUST_VMSA_PAGE_BIT; // We never want to declare pages for use for VMSA

	/* "rmpadjust" mnemonic support in binutils 2.36 and newer */
	asm volatile(".byte 0xF3,0x0F,0x01,0xFE\n\t"
		     : "=a"(rc)
		     : "a"(vaddr), "c"(rmp_psize), "d"(attrs)
		     : "memory", "cc");

	return rc; // 0: SUCCESS, 1 FAIL_INPUT illegal input parameters, 2 FAIL_PERMISSION insufficient permissions, 6 FAIL_SIZEMISMATCH Page size mismatch between guest and RMP
}

static inline int rmpadjust_allow(unsigned long vaddr, uint8_t vmpl) {
    return rmpadjust(vaddr, RMP_PG_SIZE_4K, VMPL_READ | VMPL_WRITE | VMPL_EXEC_USER | VMPL_EXEC_SUPERVISOR | VMPL_SSS | vmpl);
}

static inline int rmpadjust_deny(unsigned long vaddr, uint8_t vmpl) {
    return rmpadjust(vaddr, RMP_PG_SIZE_4K, vmpl);
}

/// Creates a ring into data_shared->ingress and ->egress
bool ring_pair_create(struct shm* data_shared) {
    next_tailq_buf = data_shared->tailq_entry_buf;
    next_alloc_buffer = data_shared->ingress.buf; // rte_ring_create will create itself in this buffer
    struct rte_ring *ring = rte_ring_create("test_ring", RING_SIZE, SOCKET_ID_ANY,
                                             RING_F_SP_ENQ | RING_F_SC_DEQ);
    next_tailq_buf = NULL;
    next_alloc_buffer = NULL;

    if (!ring) {
        println("Failed to create ingress ring");
        return false;
    }
    println("Ingress ring created: %s, count=%u", ring->name, rte_ring_count(ring));

    next_tailq_buf = data_shared->tailq_entry_buf; // we can reuse the same buffer for this new tailq, trust me bro (the entry will be the same and is not really relevant anyways)
    next_alloc_buffer = data_shared->egress.buf; // rte_ring_create will create itself in this buffer
    ring = rte_ring_create("test_ring", RING_SIZE, SOCKET_ID_ANY,
                                             RING_F_SP_ENQ | RING_F_SC_DEQ);
    next_tailq_buf = NULL;
    next_alloc_buffer = NULL;

    if (!ring) {
        println("Failed to create exgress ring");
        return false;
    }
    println("Egress ring created: %s, count=%u", ring->name, rte_ring_count(ring));

    return true;
}

struct rte_mempool* mbuf_pool_create(struct shm* data_shared) {
    struct rte_mempool *pool = data_shared->mbuf_pool;

    println("create_shm_mbuf_pool(%s, %p)", "VNFlet_MBUF_POOL", data_shared);
    next_alloc_buffer = data_shared->pool_priv; // TODO:
    next_tailq_buf = data_shared->tailq_entry_buf; // we can reuse the same buffer for this new tailq, trust me bro (the entry will be the same and is not really relevant anyways)
    next_memhdr_buf = (void*)&data_shared->pool_memhdr;
    data_shared->mbuf_pool = create_shm_mbuf_pool("VNFlet_MBUF_POOL", data_shared);
    next_alloc_buffer = NULL;
    next_tailq_buf = NULL;
    next_memhdr_buf = NULL;
    pool = data_shared->mbuf_pool;
    if (!pool) {
        printf("Failed to create shm mbuf pool\n");
        return NULL;
    }
    printf("Mbuf pool %p created with %u objects\n", pool, pool->populated_size);

    return pool;
}

#define PTE_DESCRIPTOR_ENTRIES 256
// entry 0 is the first one
struct pte_descriptor {
    uint64_t vaddrs[PTE_DESCRIPTOR_ENTRIES]; // look up vaddr by checking vaddrs[idx] where paddrs[idx] == paddr
    uint64_t paddrs[PTE_DESCRIPTOR_ENTRIES];
};

static struct pte_descriptor* vnflet_page_tables; // at runtime, shall be initialized to have CHAINING entries

/// maps page tables at >= CHANNEL(17)
void dump_vnflet_page_tables() {
    for (int i = 0; i < CHAINING; i++) {
        println("VNFlet %d page directory", i);
        println("First entry in page directory: %lu", vnflet_page_tables[i].vaddrs[0] ? *(uint64_t*)vnflet_page_tables[i].vaddrs[0] : 0);
        /* println("First entry in page directory: %lu", vnflet_page_tables[i].page_directory_vaddr ? *(uint64_t*)vnflet_page_tables[i].page_directory_vaddr : 0); */
        for (int j = 0; j < 5; j++) {
            if (vnflet_page_tables[i].vaddrs[j] != 0) {
                println("  vaddr %p <- paddr %p", (void*)vnflet_page_tables[i].vaddrs[j], (void*)vnflet_page_tables[i].paddrs[j]);
            }
        }
        println("  ...");
    }
}

void mark_present(uint64_t* pte) {
    *pte |= 1ULL; // set present bit
}
void mark_not_present(uint64_t* pte) {
    *pte &= ~1ULL; // clear present bit
}

bool is_page_present(uint64_t* pte) {
    return (*pte & 1) == 1;
}

uint64_t strip_paddr(uint64_t pte) {
    return pte & 0x0007FFFFFFFFF000ULL; // extract physical address (bits 12-50), strip C-bit (51) and flags
}

// given a paddr to a page that is part of a page table, get the vaddr at which the page is mapped
void* vaddr_to_pgtable_paddr(struct pte_descriptor* directory, uint64_t paddr) {
    for (int i = 0; i < PTE_DESCRIPTOR_ENTRIES; i++) {
        if (directory->paddrs[i] == (uint64_t)paddr) {
            return (void*)directory->vaddrs[i];
        }
    }
    return NULL;
}

uint64_t page_walk_index(uint64_t vaddr, int level) {
    return (vaddr >> (12 + level * 9)) & 0x1FF;
}

#define PGD 3
#define PUD 2
#define PMD 1
#define PTE 0

// basically a page table walk
uint64_t* pte_from_vaddr(struct pte_descriptor* directory, void* vaddr) {
    uint64_t* pgtable_page = (uint64_t*)(directory->vaddrs[0]);
    uint64_t* pte = NULL;

    for (int level = PGD; level >= PTE; level--) {
        uint64_t idx = page_walk_index((uint64_t)vaddr, level);
        pte = &(pgtable_page[idx]);
        if (level > PTE) {
            if (!is_page_present(pte))
                return NULL; // intermediate level not present
            uint64_t next_paddr = strip_paddr(*pte);
            pgtable_page = vaddr_to_pgtable_paddr(directory, next_paddr);
            if (!pgtable_page)
                return NULL;
        }
        // At PTE level, return the pointer regardless of present bit
    }
    return pte; // leaf PTE
}


void map_buffer_to_vnflet(int vnflet_id, struct rte_mbuf* mbuf) {
    debug println("map_buffer_to_vnflet: vnflet_id=%d, mbuf=%p", vnflet_id, mbuf);
    void* vaddr = rte_pktmbuf_mtod(mbuf, void *);
    struct pte_descriptor* vnflet_directory = &vnflet_page_tables[vnflet_id];
    uint64_t* pte = pte_from_vaddr(vnflet_directory, vaddr);
    if (!pte) { println("  ERROR: pte is NULL"); return; }
    mark_present(pte);
    __asm__ volatile("invlpg (%0)" :: "r"(vaddr) : "memory");
}

void unmap_buffer_from_vnflet(int vnflet_id, struct rte_mbuf* mbuf) {
    debug println("unmap_buffer_from_vnflet: vnflet_id=%d, mbuf=%p", vnflet_id, mbuf);
    void* vaddr = rte_pktmbuf_mtod(mbuf, void *);
    struct pte_descriptor* vnflet_directory = &vnflet_page_tables[vnflet_id];
    uint64_t* pte = pte_from_vaddr(vnflet_directory, vaddr);
    if (!pte) { println("  ERROR: pte is NULL"); return; }
    mark_not_present(pte);
    __asm__ volatile("invlpg (%0)" :: "r"(vaddr) : "memory");
    /* __asm__ volatile("invlpga" :: "a"(addr), "c"(asid)); // or invlpgb + tlbsync for many pages */
}

void init_pt() {
    println("get_unprivileged_page_tables");
    vnflet_page_tables = aligned_alloc(4096, sizeof(struct pte_descriptor) * CHAINING);
    assert(vnflet_page_tables != NULL && "Failed to allocate memory for page tables");
    get_unprivileged_page_tables((void*)vnflet_page_tables, sizeof(struct pte_descriptor) * CHAINING);
    dump_vnflet_page_tables();
}

void main_shm(char mode, struct shm *data_shared_iomgr, struct shm *data_shared_pool) {
    size_t num_deq = 0, num_enq = 0, total_rx = 0, total_tx = 0;
    void *deq_objs[BURST_SIZE];
    void *enq_objs[BURST_SIZE];
    delay(1); // warm up CoW triggered by delay
    struct workload* workload = workload_alloc();

    /* test keys - replace with real keys for production */
    static const uint8_t test_enc_key[16] = {
        0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef,
        0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54, 0x32, 0x10
    };
    static const uint8_t test_auth_key[16] = {
        0x10, 0x32, 0x54, 0x76, 0x98, 0xba, 0xdc, 0xfe,
        0xef, 0xcd, 0xab, 0x89, 0x67, 0x45, 0x23, 0x01
    };

    struct ipsec_sa sa;
    ipsec_sa_init(&sa, test_enc_key, test_auth_key,
                    1,    /* replay_start: initial sequence number */
                    32);  /* ooo_window: out-of-order replay window size */

    uint32_t spi = 0x1000;  /* Security Parameters Index */

    println("Initializing EAL...");

    // Initialize DPDK ring
    if (!ring_pair_create(data_shared_iomgr))
        return;

    struct rte_ring* ingress = &data_shared_iomgr->ingress.ring;
    struct rte_ring* egress = &data_shared_iomgr->egress.ring;
    struct rte_mempool* pool = data_shared_pool->mbuf_pool;
    assert(pool != NULL && "pool need to be allocated by driver");

    delayed_ns = 0;
    delays = 0;
    ids_init();

    trustlet_exit();

    uint64_t time_counter = 0;
    uint64_t pkt_counter = 0;

    while (likely(atomic_load(&data_shared_pool->keep_running))) {
#ifdef MEASURE_PER_PACKET
        uint64_t start_timer = clock_monotonic_get();
#endif

        num_deq = rte_ring_sc_dequeue_burst(ingress, deq_objs, BURST_SIZE, NULL);
        if (num_deq == 0) {
            continue;
        }
        artificial_workload(workload, num_deq);
        delay(PER_VNFLET_WORKLOAD_NS*num_deq);
#ifdef REAL_WORKLOAD
        if (mode == MODE_FIRST_NODE) {
            for (int i = 0; i < num_deq; i++) {
                ipsec_esp_encap(deq_objs[i], &sa, spi, 0);
                ipsec_chacha_encrypt_auth(deq_objs[i], &sa);
                ipsec_ip_encap(deq_objs[i], 50, 0x1, 0x2);
            }
        }
        if (mode == MODE_MIDDLE_NODE) {
            for (int i = 0; i < num_deq; i++) {
                struct rte_mbuf *pkt = deq_objs[i];
                ids_scan(rte_pktmbuf_mtod(pkt, const char *),
                         rte_pktmbuf_data_len(pkt));
            }
        }
        if (mode == MODE_LAST_NODE) {
            for (int i = 0; i < num_deq; i++) {
                ipsec_ip_decap(deq_objs[i]);
                ipsec_chacha_decrypt_auth(deq_objs[i], &sa);
                ipsec_esp_decap(deq_objs[i], &sa);
            }
        }
#endif

        num_enq = rte_ring_sp_enqueue_bulk(egress, deq_objs, num_deq, NULL);
        if (num_deq != num_enq) {
            // TODO: slitently drops mbuf right now, leaking it and never returning it to the pool.
        }
#ifdef MEASURE_PER_PACKET
        time_counter += clock_monotonic_get() - start_timer;
        pkt_counter += num_deq;
#endif
    }

#ifdef MEASURE_PER_PACKET
    println("Time per packet ! %.2f ns", pkt_counter > 0 ? (double) time_counter / (double) pkt_counter : 0);
#endif

    println("Average per vnflet workload delay: %.2f ns (total delayed ns: %lu over %lu iterations)", delays > 0 ? (double)delayed_ns / (double)delays : 0, delayed_ns, delays);

    notify_monitor();
}

void main_iomgr(struct shm *data_shared_previous, struct shm *data_shared_next) {
    init_pt();

    struct shm* buf = data_shared_previous;
    size_t buf_used = 0;
    size_t num_deq = 0, num_enq = 0, total_rx = 0, total_tx = 0;
    void *deq_objs[BURST_SIZE];
    void *enq_objs[BURST_SIZE];
    delay(1); // warm up CoW triggered by delay

    // Initialize DPDK EAL with --no-huge for environments without hugepages
    println("Initializing EAL...");
    /* char *eal_args[] = {"slick_vnflet", "--no-huge"}; */
    /* int eal_argc = sizeof(eal_args) / sizeof(eal_args[0]); */
    /* int ret = rte_eal_init(eal_argc, eal_args); */
    /* if (ret < 0) { */
    /*     println("Failed to initialize EAL: %s\n", rte_strerror(rte_errno)); */
    /*     return -1; */
    /* } */

    // Initialize DPDK ring
    if (!ring_pair_create(data_shared_previous))
        return;

    struct rte_mempool* pool1 = NULL;
    // Allocated by driver:
    // // Create mbuf pool backed by shared memory
    // struct rte_mempool *pool1 = mbuf_pool_create(data_shared_previous);
    // if (!pool1)
    //     return;

    data_shared_previous->keep_running = true;


    // Initialize DPDK ring
    struct rte_mempool *pool2 = data_shared_next->mbuf_pool;
    if (!ring_pair_create(data_shared_next))
        return;

    pool2 = mbuf_pool_create(data_shared_next);
    if (!pool2)
        return;

    struct shm* shm_trustlet[CHAINING];
    for (int i = 0 ; i < CHAINING; i++) {
        shm_trustlet[i] = CHANNEL_ADDR(2+i);
    }

    trustlet_exit();

    /* println("Waiting for pool2 to be allocated by next VNFlet..."); */
    /* while (READ_ONCE(data_shared_next->mbuf_pool) == NULL) {} */
    pool1 = data_shared_previous->mbuf_pool;
    pool2 = data_shared_next->mbuf_pool;
    // data_shared_next mbuf pool is always allocated by the next VNFlet (or the driver in case of MODE_LAST_NODE)
    /* if (mode != MODE_LAST_NODE) { // last node pool allocated by driver */
    /*     // Create mbuf pool backed by shared memory */
    /*     data_shared_next->mbuf_pool = create_shm_mbuf_pool(data_shared_next); */
    /*     pool2 = data_shared_next->mbuf_pool; */
    /*     if (!pool2) { */
    /*         printf("Failed to create shm mbuf pool\n"); */
    /*         return; */
    /*     } */
    /*     printf("Mbuf pool created with %u objects\n", pool2->populated_size); */
    /* } */
    printf("Require pool %p\n", pool2);
    assert(pool1 != NULL && "pool1 need to be allocated by driver");
    assert(pool2 != NULL && "pool2 need to be allocated by someone else");

    uint64_t duration_ns = 15ULL * 1000000000ULL; // 15 seconds
    uint64_t check_interval = 1e6;
    uint64_t start_time = clock_monotonic_get();
    uint64_t end_time = start_time + duration_ns;
    uint64_t iterations = 0;
    char local_bufs[BURST_SIZE][SHM_POOL_DATA_ROOM];
    size_t local_buf_lens[BURST_SIZE];

    while (likely(atomic_load(&data_shared_previous->keep_running))) {
        iterations++;
        /* delay(1*1e9); */
        /* buf_used = trustlet_rx(buf); */
        /* buf->data[3] += 1; */
        /* trustlet_tx(buf, buf_used); */

        // driver -> iomgr -> VNFlet 0
        num_deq = rte_ring_sc_dequeue_burst(&data_shared_previous->ingress.ring, deq_objs, BURST_SIZE, NULL); // pool1 bufs
        debug println("%lu = rte_ring_sc_dequeue_burst(%p, ...)", num_deq, &data_shared_previous->ingress.ring);

        if(num_deq == 0) {
            /* vnflet_stats[vnfletId].dequeue_failures++; */
        } else {
            total_rx += num_deq;
            debug println("Dequeued %lu objects from ring. First: %p", num_deq, deq_objs[0]);

            /* nop_delay(100); // RMPADJUST */
            rmpadjust_deny((unsigned long)rte_pktmbuf_mtod((struct rte_mbuf*)(deq_objs[0]), void *), VMPL3); // revoke guest access

            // pass buffers to first VNFlet
            num_enq = rte_ring_sp_enqueue_bulk(&shm_trustlet[0]->ingress.ring, deq_objs, num_deq, NULL);
            if (num_enq == 0) {
                /* rte_pktmbuf_free_bulk((struct rte_mbuf **)enq_objs, num_deq); */
                // TODO: We need to drop the packet now, so don't we have to pass it back to the driver? enqueue_bulk(data_shared_previous->egress) or data_shared_next->ingress with pktsize 0 or so? Actually, we must ensure that this enq never fails though!
            } else {
                total_tx += num_enq;
                debug println("Enqueued %lu objects to ring.", num_enq);
            }
        }

        // VNFlet n -> iomgr -> VNFlet n+1
        for (int i = 0; i < CHAINING-1; i++) {
            num_deq = rte_ring_sc_dequeue_burst(&shm_trustlet[i]->egress.ring, deq_objs, BURST_SIZE, NULL);
            if (num_deq == 0) {
                continue;
            }
            // TODO: stub operation
            unmap_buffer_from_vnflet(i, deq_objs[0]);
            map_buffer_to_vnflet(i, deq_objs[0]);
            // nop_delay(100); // change pte
            num_enq = rte_ring_sp_enqueue_bulk(&shm_trustlet[i+1]->ingress.ring, deq_objs, num_deq, NULL);
            if (num_deq != num_enq) {
                // TODO: We need to drop the packet now, so don't we have to pass it back to the driver? enqueue_bulk(data_shared_previous->egress) or data_shared_next->ingress with pktsize 0 or so? Actually, we must ensure that this enq never fails though!
            }
        }

        // VNFlet CHAINING-1 -> iomgr -> driver
        num_deq = rte_ring_sc_dequeue_burst(&shm_trustlet[CHAINING-1]->egress.ring, deq_objs, BURST_SIZE, NULL);
        if (num_deq == 0) {
        } else {
            /* nop_delay(100); // RMPADJUST */
            rmpadjust_allow((unsigned long)rte_pktmbuf_mtod((struct rte_mbuf*)(deq_objs[0]), void *), VMPL3); // revoke guest access
            num_enq = rte_ring_sp_enqueue_bulk(&data_shared_next->ingress.ring, deq_objs, num_deq, NULL);
            if (num_deq != num_enq) {
                // TODO: We need to drop the packet now, so don't we have to pass it back to the driver? enqueue_bulk(data_shared_previous->egress) or data_shared_next->ingress with pktsize 0 or so? Actually, we must ensure that this enq never fails though!
            }
        }

        /* num_enq = rte_ring_sp_enqueue_bulk(&buf->egress.ring, (void**)(&(deq_objs[0])), num_deq, NULL); */
        /* total_tx += num_enq; */
        /* debug println("Enqueued %lu objects to ring.", num_enq); */

        /* ndelay(workload_cycles); */

        /* num_enq = rte_ring_sp_enqueue_bulk(TODO, deq_objs, num_deq, NULL); */
    }
    atomic_store(&data_shared_next->keep_running, false); // signal next trustlet to stop as well
    uint64_t elapsed_ns = clock_monotonic_get() - start_time;
    println("Finished %lu iterations in %.1f s, total_rx=%lu", iterations, elapsed_ns / 1e9, total_rx);
    delay(1*1e9); // try to mitigate print interleaving
    notify_monitor();
}

// Acts as load generator and sink for VNFlet 0 and measures its throughput.
// Pure ring ping: no rmpadjust/PTE ops on the measured packets.
// mbufs are taken once from the driver-created pool in data_shared_previous --
// popped raw off the shm_stack, because the rte_mempool ops_index the driver
// stored is not valid in this process -- and recirculated forever, so the hot
// loop does no alloc/free. Results go to data_shared_next->loadgen_results.
void main_iomgr_loadgen(struct shm *data_shared_previous, struct shm *data_shared_next) {
    void *deq_objs[BURST_SIZE];
    struct rte_mbuf *bufs[LOADGEN_INFLIGHT];
    delay(1); // warm up CoW triggered by delay

    // VNFlet 0's ring pair (rings created by VNFlet 0 during its config invocation)
    struct shm* vnflet0 = (struct shm*)CHANNEL_ADDR(2);

    struct shm_stack *stack = &data_shared_previous->pool_stack;
    if (stack->top < LOADGEN_INFLIGHT) {
        println("loadgen: pool has only %u mbufs, need %d", stack->top, LOADGEN_INFLIGHT);
        return;
    }
    for (int i = 0; i < LOADGEN_INFLIGHT; i++) {
        struct rte_mbuf *m = (struct rte_mbuf *)stack->objs[--stack->top];
        m->data_off = RTE_PKTMBUF_HEADROOM;
        m->data_len = PACKET_SIZE;
        m->pkt_len = PACKET_SIZE;
        m->nb_segs = 1;
        m->next = NULL;
        memset(rte_pktmbuf_mtod(m, void *), 0xab, PACKET_SIZE);
        bufs[i] = m;
    }
    println("loadgen: %d mbufs of %d bytes in flight to VNFlet 0", LOADGEN_INFLIGHT, PACKET_SIZE);

    trustlet_exit();

    uint64_t start_ns = clock_monotonic_get();
    uint64_t total = 0, lost = 0;

    // prime: hand all mbufs to VNFlet 0
    if (rte_ring_sp_enqueue_bulk(&vnflet0->ingress.ring, (void **)bufs, LOADGEN_INFLIGHT, NULL) == 0) {
        println("loadgen: failed to prime VNFlet 0 ingress ring");
        notify_monitor();
        return;
    }

    while (likely(atomic_load(&data_shared_previous->keep_running))) {
        size_t num_deq = rte_ring_sc_dequeue_burst(&vnflet0->egress.ring, deq_objs, BURST_SIZE, NULL);
        if (num_deq == 0)
            continue;
        total += num_deq;
#ifdef REAL_WORKLOAD
        // first-node encap grows the packets each round trip; reset before recirculating
        for (size_t i = 0; i < num_deq; i++) {
            struct rte_mbuf *m = (struct rte_mbuf *)deq_objs[i];
            m->data_off = RTE_PKTMBUF_HEADROOM;
            m->data_len = PACKET_SIZE;
            m->pkt_len = PACKET_SIZE;
        }
#endif
        // cannot fail: at most LOADGEN_INFLIGHT mbufs are in flight, which fits the ring
        if (rte_ring_sp_enqueue_bulk(&vnflet0->ingress.ring, deq_objs, num_deq, NULL) == 0)
            lost += num_deq;
    }
    uint64_t elapsed_ns = clock_monotonic_get() - start_ns;

    data_shared_next->loadgen_results.packets = total;
    data_shared_next->loadgen_results.elapsed_ns = elapsed_ns;

    println("loadgen finished: %lu packets in %.1f s = %.3f Mpps (lost: %lu)",
            total, elapsed_ns / 1e9, elapsed_ns ? total / (elapsed_ns / 1e9) / 1e6 : 0.0, lost);
    delay(1*1e9); // try to mitigate print interleaving
    notify_monitor();
}

void main_default(bool suppress_output) {
    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    trustlet_exit();

    while (1) {
        memcpy(output, input, DATA_SIZE);

        if (suppress_output) {
            output[1] += 1;
            printf("Trustlet processed: ");
            hexdump(output, DATA_SIZE);
            trustlet_exit();
        } else {
            output[2] += 1;
            printf("Trustlet processed: ");
            hexdump(output, DATA_SIZE);
            notify_monitor();
        }
    }
}

int main(int argc, char** argv) {
    println("Trustlet main at %p", main);

    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    finalize_zygote();
    int type = 0;

    println("malloc start");
    char* buf = malloc(2097152);
    println("malloc end");

    println("main exit enter");
    trustlet_exit();
    println("main exit exit");

    struct trustlet_configuration *config = (struct trustlet_configuration *)input;

    if(config->mode[0] == MODE_FIRST_NODE || config->mode[0] == MODE_MIDDLE_NODE || config->mode[0] == MODE_LAST_NODE){
        main_shm(config->mode[0], config->shm_addr_previous, config->shm_addr_next);
    } else if(config->mode[0] == MODE_IOMGR_NODE) {
        main_iomgr(config->shm_addr_previous, config->shm_addr_next);
    } else if(config->mode[0] == MODE_IOMGR_LOADGEN) {
        main_iomgr_loadgen(config->shm_addr_previous, config->shm_addr_next);
    } else if(config->mode[0] == 'x'){
        bool suppress_output = false;
        main_default(suppress_output);
    } else {
        bool suppress_output = true;
        main_default(suppress_output);
    }
}
