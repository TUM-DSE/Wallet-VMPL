#ifndef SHM_MEMPOOL_H
#define SHM_MEMPOOL_H

#include <errno.h>
#include <stdio.h>
#include <rte_mempool.h>
#include <rte_mbuf.h>
#include <rte_errno.h>

#include "util.h"

// Cross-VMPL spinlock for the shared mbuf pool stack. The critical sections are a
// handful of pointer moves, so an uncontended test-and-set is ~free; with
// cache_size=0 (see create_shm_mbuf_pool) every alloc/free takes it, which is
// exactly what makes the un-locked version race so pervasively. Define
// -DSHM_STACK_NO_LOCK to get the old (racy) behaviour for A/B measurement.
static inline void shm_stack_lock(struct shm_stack *s)
{
#ifndef SHM_STACK_NO_LOCK
	while (atomic_flag_test_and_set_explicit(&s->lock, memory_order_acquire))
		__asm__ __volatile__("pause");
#else
	(void)s;
#endif
}
static inline void shm_stack_unlock(struct shm_stack *s)
{
#ifndef SHM_STACK_NO_LOCK
	atomic_flag_clear_explicit(&s->lock, memory_order_release);
#else
	(void)s;
#endif
}

// Optional double-alloc / double-free detector -- PROOF that the pool stack is
// racing. Gated by -DSHM_POOL_DEBUG. Stamps each mbuf's spare dynfield2 with an
// ALLOC/FREE marker; a pop that finds an object still marked ALLOC (or a push
// finding it still FREE) means the same buffer has two live references at once --
// i.e. the cross-VMPL double allocation. The marker lives in the shared mbuf, so
// this catches the race across the driver<->trustlet boundary. Off by default and
// independent of the lock, so you can run: (no lock + debug) -> expect reports;
// (lock + debug) -> expect none.
#ifdef SHM_POOL_DEBUG
#define SHM_TAG_ALLOC 0xA110CULL
#define SHM_TAG_FREE  0xF7EE0ULL
static inline void shm_dbg_on_alloc(void *o)
{
	struct rte_mbuf *m = (struct rte_mbuf *)o;
	static unsigned long reported;
	if (m->dynfield1[8] == SHM_TAG_ALLOC && reported++ < 200)
		printf("SHM-RACE double-alloc: mbuf %p handed out while still allocated\n", o);
	m->dynfield1[8] = SHM_TAG_ALLOC;
}
static inline void shm_dbg_on_free(void *o)
{
	struct rte_mbuf *m = (struct rte_mbuf *)o;
	static unsigned long reported;
	if (m->dynfield1[8] == SHM_TAG_FREE && reported++ < 200)
		printf("SHM-RACE double-free: mbuf %p freed while already free\n", o);
	m->dynfield1[8] = SHM_TAG_FREE;
}
#else
#define shm_dbg_on_alloc(o) ((void)0)
#define shm_dbg_on_free(o)  ((void)0)
#endif

static int
shm_stack_alloc(struct rte_mempool *mp)
{
	struct shm_stack *s = (struct shm_stack *)mp->pool_config;
	s->size = mp->size;
	s->top = 0;
	atomic_flag_clear(&s->lock);
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
	shm_stack_lock(s);
	if (s->top + n > s->size) {
		shm_stack_unlock(s);
		return -ENOBUFS;
	}
	for (unsigned int i = 0; i < n; i++) {
		shm_dbg_on_free(obj_table[i]);
		s->objs[s->top++] = (void *)obj_table[i];
	}
	shm_stack_unlock(s);
	return 0;
}

static int
shm_stack_dequeue(struct rte_mempool *mp, void **obj_table, unsigned int n)
{
	struct shm_stack *s = (struct shm_stack *)mp->pool_data;
	shm_stack_lock(s);
	if (s->top < n) {
		shm_stack_unlock(s);
		return -ENOBUFS;
	}
	for (unsigned int i = 0; i < n; i++) {
		obj_table[i] = s->objs[--s->top];
		shm_dbg_on_alloc(obj_table[i]);
	}
	shm_stack_unlock(s);
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
create_shm_mbuf_pool(char *name, struct shm *shared)
{
	unsigned n = SHM_POOL_SIZE;
	unsigned elt_size = sizeof(struct rte_mbuf) + SHM_POOL_DATA_ROOM;
	unsigned priv_size = sizeof(struct rte_pktmbuf_pool_private);

	/* NO_IOVA_CONTIG: this pool lives in shared memory and is never handed
	 * to a device for DMA (the driver copies into its NIC pool first), so
	 * objects may cross page boundaries. Without it, populate refuses to
	 * split objects across the 4K no-huge pages and fits only ONE ~2.4KB
	 * element per page -- 888 of 1536 objects, wasting 42% of pool_buf. */
	struct rte_mempool *mp = rte_mempool_create_empty(
		name, n, elt_size, 0, priv_size,
		SOCKET_ID_ANY, RTE_MEMPOOL_F_NO_IOVA_CONTIG);
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

	/* Pass the data room EXPLICITLY: with a NULL opaque, pool_init derives
	 * it as elt_size - sizeof(rte_mbuf), but the mempool pads elt_size (e.g.
	 * 65663 -> 65664), and the derived 65536 wraps the uint16_t room to 0 --
	 * every mbuf then reports buf_len 0 and RX queue setup rejects the pool. */
	struct rte_pktmbuf_pool_private mbp_priv = {
		.mbuf_data_room_size = SHM_POOL_DATA_ROOM,
		.mbuf_priv_size = 0,
	};
	rte_pktmbuf_pool_init(mp, &mbp_priv);

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
