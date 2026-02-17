#ifndef SHM_MEMPOOL_H
#define SHM_MEMPOOL_H

#include <errno.h>
#include <stdio.h>
#include <rte_mempool.h>
#include <rte_mbuf.h>
#include <rte_errno.h>

#include "util.h"

static int
shm_stack_alloc(struct rte_mempool *mp)
{
	struct shm_stack *s = (struct shm_stack *)mp->pool_config;
	s->size = mp->size;
	s->top = 0;
	mp->pool_data = s;
	return 0;
}

static void
shm_stack_free(struct rte_mempool *mp)
{
	(void)mp;
}

static int
shm_stack_enqueue(struct rte_mempool *mp, void * const *obj_table,
		  unsigned int n)
{
	struct shm_stack *s = (struct shm_stack *)mp->pool_data;
	if (s->top + n > s->size)
		return -ENOBUFS;
	for (unsigned int i = 0; i < n; i++)
		s->objs[s->top++] = (void *)obj_table[i];
	return 0;
}

static int
shm_stack_dequeue(struct rte_mempool *mp, void **obj_table, unsigned int n)
{
	struct shm_stack *s = (struct shm_stack *)mp->pool_data;
	if (s->top < n)
		return -ENOBUFS;
	for (unsigned int i = 0; i < n; i++)
		obj_table[i] = s->objs[--s->top];
	return 0;
}

static unsigned
shm_stack_get_count(const struct rte_mempool *mp)
{
	const struct shm_stack *s = (const struct shm_stack *)mp->pool_data;
	return s->top;
}

static const struct rte_mempool_ops shm_stack_ops = {
	.name = "shm_stack",
	.alloc = shm_stack_alloc,
	.free = shm_stack_free,
	.enqueue = shm_stack_enqueue,
	.dequeue = shm_stack_dequeue,
	.get_count = shm_stack_get_count,
};

RTE_MEMPOOL_REGISTER_OPS(shm_stack_ops);

static inline struct rte_mempool *
create_shm_mbuf_pool(struct shm *shared)
{
	unsigned n = SHM_POOL_SIZE;
	unsigned elt_size = sizeof(struct rte_mbuf) + SHM_POOL_DATA_ROOM;
	unsigned priv_size = sizeof(struct rte_pktmbuf_pool_private);

	struct rte_mempool *mp = rte_mempool_create_empty(
		"shm_mbuf_pool", n, elt_size, 0, priv_size,
		SOCKET_ID_ANY, 0);
	if (!mp) {
		printf("Failed to create empty mempool: %s\n",
		       rte_strerror(rte_errno));
		return NULL;
	}

	int ret = rte_mempool_set_ops_byname(mp, "shm_stack",
					     &shared->pool_stack);
	if (ret != 0) {
		printf("Failed to set mempool ops: %d\n", ret);
		rte_mempool_free(mp);
		return NULL;
	}

	/* Call our alloc callback directly since rte_mempool_ops_alloc
	 * is not exported from the shared library. */
	ret = shm_stack_alloc(mp);
	if (ret != 0) {
		printf("Failed to alloc mempool ops: %d\n", ret);
		rte_mempool_free(mp);
		return NULL;
	}

	rte_pktmbuf_pool_init(mp, NULL);

	int cnt = rte_mempool_populate_iova(mp, shared->pool_buf,
					    RTE_BAD_IOVA,
					    SHM_POOL_BUF_SIZE, NULL, NULL);
	if (cnt <= 0) {
		printf("Failed to populate mempool: %d\n", cnt);
		rte_mempool_free(mp);
		return NULL;
	}
	printf("Populated %d objects in mempool\n", cnt);

	rte_mempool_obj_iter(mp, rte_pktmbuf_init, NULL);

	return mp;
}

#endif /* SHM_MEMPOOL_H */
