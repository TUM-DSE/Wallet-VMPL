// pktmbuf_pool.h - Simple non-atomic stack-based DPDK mempool backend ("spool")
//
// Single-threaded LIFO pool with no atomics and no locking.
// Useful as a baseline or when the pool is only accessed from one core.
//
// Usage:
//   #include "pktmbuf_pool.h"
//
//   // Option A: create pool manually
//   struct rte_mempool *mp = rte_mempool_create_empty(...);
//   rte_mempool_set_ops_byname(mp, "spool", &g_spool);
//   ...
//
//   // Option B: use the helper
//   struct rte_mempool *mp = spool_pktmbuf_pool_create("name", n, cache, socket);

#ifndef PKTMBUF_POOL_H
#define PKTMBUF_POOL_H

#include <errno.h>
#include <rte_mempool.h>
#include <rte_mbuf.h>
#include <rte_errno.h>

#ifndef SPOOL_MAX
#define SPOOL_MAX 65536
#endif

struct spool {
    uint32_t size;
    uint32_t top;
    void *objs[SPOOL_MAX];
};

static struct spool g_spool;

static int spool_alloc(struct rte_mempool *mp) {
    struct spool *s = (struct spool *)mp->pool_config;
    s->size = mp->size;
    s->top = 0;
    mp->pool_data = s;
    return 0;
}

static void spool_free(struct rte_mempool *mp) { (void)mp; }

static int spool_enqueue(struct rte_mempool *mp, void *const *obj_table, unsigned n) {
    struct spool *s = mp->pool_data;
    if (s->top + n > s->size) return -ENOBUFS;
    for (unsigned i = 0; i < n; i++)
        s->objs[s->top++] = (void *)obj_table[i];
    return 0;
}

static int spool_dequeue(struct rte_mempool *mp, void **obj_table, unsigned n) {
    struct spool *s = mp->pool_data;
    if (s->top < n) return -ENOBUFS;
    for (unsigned i = 0; i < n; i++)
        obj_table[i] = s->objs[--s->top];
    return 0;
}

static unsigned spool_get_count(const struct rte_mempool *mp) {
    return ((const struct spool *)mp->pool_data)->top;
}

static const struct rte_mempool_ops spool_ops = {
    .name = "spool",
    .alloc = spool_alloc,
    .free = spool_free,
    .enqueue = spool_enqueue,
    .dequeue = spool_dequeue,
    .get_count = spool_get_count,
};
RTE_MEMPOOL_REGISTER_OPS(spool_ops);

// Helper: create a pktmbuf pool backed by spool.
static inline struct rte_mempool *
spool_pktmbuf_pool_create(const char *name, unsigned n,
                           unsigned cache_size, int socket_id)
{
    unsigned elt = sizeof(struct rte_mbuf) + RTE_MBUF_DEFAULT_BUF_SIZE;
    struct rte_mempool *mp = rte_mempool_create_empty(
        name, n, elt, cache_size,
        sizeof(struct rte_pktmbuf_pool_private),
        socket_id, 0);
    if (!mp)
        return NULL;
    if (rte_mempool_set_ops_byname(mp, "spool", &g_spool) != 0) {
        rte_mempool_free(mp);
        return NULL;
    }
    rte_pktmbuf_pool_init(mp, NULL);
    if (rte_mempool_populate_default(mp) < 0) {
        rte_mempool_free(mp);
        return NULL;
    }
    rte_mempool_obj_iter(mp, rte_pktmbuf_init, NULL);
    return mp;
}

#endif /* PKTMBUF_POOL_H */
