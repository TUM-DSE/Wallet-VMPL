// mempool_comparison.c - Benchmark alloc/free throughput of DPDK mempool backends
//
// Usage:
//   ./mempool_comparison --no-huge -l 0 [-- <backend> [cache_size]]
//
// Without arguments after '--': runs all backends with cache sizes 0, 32, 256.
// With arguments:  runs a single backend, e.g.  -- ring_sp_sc 32
//
// Backends: ring_mp_mc  ring_sp_sc  ring_mt_rts  ring_mt_hts
//           stack  lf_stack  bucket  spool

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <inttypes.h>
#include <errno.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>

#include <rte_eal.h>
#include <rte_cycles.h>
#include <rte_mempool.h>
#include <rte_mbuf.h>
#include <rte_errno.h>

#include "pktmbuf_pool.h"

// ---------------------------------------------------------------------------
// perf counter helpers
// ---------------------------------------------------------------------------

static int
perf_event_open(struct perf_event_attr *attr, pid_t pid, int cpu,
                int group_fd, unsigned long flags)
{
    return syscall(__NR_perf_event_open, attr, pid, cpu, group_fd, flags);
}

static int perf_fd = -1;

static void
perf_init(void)
{
    struct perf_event_attr pe = {
        .type = PERF_TYPE_HARDWARE,
        .size = sizeof(pe),
        .config = PERF_COUNT_HW_INSTRUCTIONS,
        .disabled = 1,
        .exclude_kernel = 1,
        .exclude_hv = 1,
    };
    perf_fd = perf_event_open(&pe, 0, -1, -1, 0);
    if (perf_fd < 0)
        fprintf(stderr, "warning: perf_event_open failed (%s), IPC will be 0\n",
                strerror(errno));
}

static inline void perf_reset_and_enable(void) {
    if (perf_fd >= 0) {
        ioctl(perf_fd, PERF_EVENT_IOC_RESET, 0);
        ioctl(perf_fd, PERF_EVENT_IOC_ENABLE, 0);
    }
}

static inline uint64_t perf_disable_and_read(void) {
    uint64_t insns = 0;
    if (perf_fd >= 0) {
        ioctl(perf_fd, PERF_EVENT_IOC_DISABLE, 0);
        read(perf_fd, &insns, sizeof(insns));
    }
    return insns;
}

// ---------------------------------------------------------------------------
// benchmark config
// ---------------------------------------------------------------------------

#ifndef NUM_MBUFS
#define NUM_MBUFS 8192
#endif

#ifndef BURST_SIZE
#define BURST_SIZE 32
#endif

#ifndef NUM_ITERATIONS
#define NUM_ITERATIONS 8000000
#endif

#define WARMUP_ITERATIONS 50000

// ---------------------------------------------------------------------------
// pool helpers
// ---------------------------------------------------------------------------

static unsigned pool_id;

static struct rte_mempool *
create_pool(const char *ops_name, unsigned cache_size)
{
    char name[RTE_MEMPOOL_NAMESIZE];
    snprintf(name, sizeof(name), "bench_%u", pool_id++);

    struct rte_mempool *mp = rte_mempool_create_empty(
        name, NUM_MBUFS,
        sizeof(struct rte_mbuf) + RTE_MBUF_DEFAULT_BUF_SIZE,
        cache_size, sizeof(struct rte_pktmbuf_pool_private),
        rte_socket_id(), 0);
    if (!mp) {
        fprintf(stderr, "  create_empty failed: %s\n", rte_strerror(rte_errno));
        return NULL;
    }

    void *pool_cfg = NULL;
    if (strcmp(ops_name, "spool") == 0)
        pool_cfg = &g_spool;

    if (rte_mempool_set_ops_byname(mp, ops_name, pool_cfg) != 0) {
        fprintf(stderr, "  set_ops_byname('%s') failed: %s\n",
                ops_name, rte_strerror(rte_errno));
        rte_mempool_free(mp);
        return NULL;
    }

    rte_pktmbuf_pool_init(mp, NULL);

    if (rte_mempool_populate_default(mp) < 0) {
        fprintf(stderr, "  populate failed: %s\n", rte_strerror(rte_errno));
        rte_mempool_free(mp);
        return NULL;
    }

    rte_mempool_obj_iter(mp, rte_pktmbuf_init, NULL);
    return mp;
}

// ---------------------------------------------------------------------------
// measurement
// ---------------------------------------------------------------------------

static void
bench(struct rte_mempool *mp, const char *name, unsigned cache_size)
{
    struct rte_mbuf *bufs[BURST_SIZE];
    int ret;

    for (unsigned i = 0; i < WARMUP_ITERATIONS; i++) {
        ret = rte_pktmbuf_alloc_bulk(mp, bufs, BURST_SIZE);
        if (ret == 0)
            rte_pktmbuf_free_bulk(bufs, BURST_SIZE);
    }

    perf_reset_and_enable();
    uint64_t start = rte_rdtsc_precise();
    for (unsigned i = 0; i < NUM_ITERATIONS; i++) {
        ret = rte_pktmbuf_alloc_bulk(mp, bufs, BURST_SIZE);
        if (unlikely(ret != 0))
            break;
        rte_pktmbuf_free_bulk(bufs, BURST_SIZE);
    }
    uint64_t end = rte_rdtsc_precise();
    uint64_t insns = perf_disable_and_read();

    uint64_t total_ops   = (uint64_t)NUM_ITERATIONS * BURST_SIZE;
    uint64_t total_cycles = end - start;
    double cyc  = (double)total_cycles / total_ops;
    double ns   = cyc / ((double)rte_get_tsc_hz() / 1e9);
    double mops = (double)total_ops / total_cycles * rte_get_tsc_hz() / 1e6;
    double ipc  = (total_cycles > 0) ? (double)insns / total_cycles : 0.0;

    printf("%-16s  cache=%-4u  %8.1f cyc/obj  %6.1f ns/obj  %8.2f Mops  IPC=%.2f\n",
           name, cache_size, cyc, ns, mops, ipc);
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

static const char *all_backends[] = {
    "ring_mp_mc", "ring_sp_sc", "ring_mt_rts", "ring_mt_hts",
    "stack", "lf_stack", "bucket", "spool",
};
#define N_BACKENDS (sizeof(all_backends) / sizeof(all_backends[0]))

int main(int argc, char **argv)
{
    int ret = rte_eal_init(argc, argv);
    if (ret < 0)
        rte_exit(EXIT_FAILURE, "EAL init failed\n");
    argc -= ret;
    argv += ret;

    perf_init();

    printf("\nMempool alloc/free benchmark  (burst=%u, iters=%u, pool=%u)\n",
           BURST_SIZE, NUM_ITERATIONS, NUM_MBUFS);
    printf("CPU: %.2f GHz\n\n", (double)rte_get_tsc_hz() / 1e9);

    if (argc > 1) {
        const char *backend = argv[1];
        unsigned cache = (argc > 2) ? (unsigned)atoi(argv[2]) : 0;

        struct rte_mempool *mp = create_pool(backend, cache);
        if (!mp)
            rte_exit(EXIT_FAILURE, "Failed to create pool '%s'\n", backend);
        bench(mp, backend, cache);
        rte_mempool_free(mp);
    } else {
        static unsigned caches[] = { 0, 32, 256 };

        for (unsigned c = 0; c < sizeof(caches) / sizeof(caches[0]); c++) {
            if (c > 0) printf("\n");
            for (unsigned b = 0; b < N_BACKENDS; b++) {
                struct rte_mempool *mp = create_pool(all_backends[b], caches[c]);
                if (!mp) {
                    printf("%-16s  cache=%-4u  FAILED\n",
                           all_backends[b], caches[c]);
                    continue;
                }
                bench(mp, all_backends[b], caches[c]);
                rte_mempool_free(mp);
            }
        }
    }

    printf("\n");
    if (perf_fd >= 0)
        close(perf_fd);
    rte_eal_cleanup();
    return 0;
}
