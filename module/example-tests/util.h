#ifndef UTIL_H
#define UTIL_H

#include <stddef.h>
#include <stdatomic.h>
#include <stdbool.h>

#include <rte_tailq.h>
#include <rte_ring.h>
#include <rte_mempool.h>
#include <rte_mbuf.h>

#define BUFFER_SIZE 1600

#ifndef BURST_SIZE
#define BURST_SIZE 1
#endif

#define CACHE_LINE_SIZE 64

#define SHARED_SIZE (4*1024*1024)

#define NUM_RINGS 2
#define RING_SIZE 1024
#define RING_BUF_SIZE RTE_ALIGN(sizeof(struct rte_ring) + (ssize_t)RING_SIZE * sizeof(void*), RTE_CACHE_LINE_SIZE)
#define TAILQ_ENTRY_SIZE sizeof(struct rte_tailq_entry)

// Number of rte_mbuf objects in the shared mempool (>= 2*RING_SIZE so the pool
// can never be exhausted by both rings' worth of in-flight mbufs)
#define SHM_POOL_SIZE (RING_SIZE - 1)
// Packet data buffer size per mbuf (128 bytes headroom + 128 bytes payload)
#define SHM_POOL_DATA_ROOM (RTE_PKTMBUF_HEADROOM + 1522)
// Backing memory for mbuf objects: each element is objhdr + rte_mbuf + data room,
// padded to cache line. Use 512 bytes/element to account for alignment variance.
#define SHM_POOL_ELT_TOTAL RTE_ALIGN(sizeof(struct rte_mempool_objhdr) + sizeof(struct rte_mbuf) + SHM_POOL_DATA_ROOM, RTE_CACHE_LINE_SIZE)
#define SHM_POOL_BUF_SIZE  (SHM_POOL_SIZE * SHM_POOL_ELT_TOTAL)

// Some primitives like create_channel(_at) work on page level 3, requiring 512G-alignment.
// The two before shared is used by the default INPUT and OUTPUT
#define CHANNEL_ADDR(x) ((void*)(0x80000000000ULL+ (x) * 0x8000000000ULL))
#define SHARED_ADDR CHANNEL_ADDR(0)

struct shm_stack {
  uint32_t size;
  uint32_t top;
  void *objs[SHM_POOL_SIZE];
};


#ifndef DEBUG
#define DEBUG 0
#endif

#if DEBUG
#define debug
#else
#define debug if(0)
#endif

struct trustlet_configuration {
#define MODE_FIRST_NODE '1'
#define MODE_MIDDLE_NODE '2'
#define MODE_LAST_NODE '3'
#define MODE_IOMGR_NODE '4'
  char mode[1];
  void* shm_addr_previous; // previous VNFlets or driver
  void* shm_addr_next; // next VNFlet or driver
};

struct buffer {
  atomic_bool trustlet_owned;
  size_t data_used;
  char data[BUFFER_SIZE];
};

struct shm {
  struct buffer legacy_buffer; // TODO remove backwards compatibility

  atomic_bool keep_running; // used as termination signal for long-running trustlets

  char tailq_entry_buf[TAILQ_ENTRY_SIZE] __attribute__((aligned(CACHE_LINE_SIZE)));
  struct rte_mempool *mbuf_pool;

  union {
    struct rte_ring ring;
    char buf[RING_BUF_SIZE];
  } ingress __attribute__((aligned(CACHE_LINE_SIZE)));

  union {
    struct rte_ring ring;
    char buf[RING_BUF_SIZE];
  } egress __attribute__((aligned(CACHE_LINE_SIZE)));

  struct shm_stack pool_stack __attribute__((aligned(CACHE_LINE_SIZE)));
  char pool_buf[SHM_POOL_BUF_SIZE] __attribute__((aligned(CACHE_LINE_SIZE)));
// (size + MASK & MASK) to align for mempool cache size 0
#define POOL_PRIV_SIZE (((sizeof(struct rte_pktmbuf_pool_private) + RTE_MEMPOOL_HEADER_SIZE((struct rte_mempool*)0x1, 0))+ RTE_MEMPOOL_ALIGN_MASK) & (~RTE_MEMPOOL_ALIGN_MASK))
  char pool_priv[POOL_PRIV_SIZE] __attribute__((aligned(CACHE_LINE_SIZE)));
  struct rte_mempool_memhdr pool_memhdr;
};

// Trustlet side: wait until we own the buffer, return data length
static inline size_t trustlet_rx(struct buffer* buf) {
  while (!atomic_load_explicit(&buf->trustlet_owned, memory_order_acquire)) {
    // spin wait
  }
  return buf->data_used;
}

// Trustlet side: set data length and release ownership to driver
static inline void trustlet_tx(struct buffer* buf, size_t len) {
  buf->data_used = len;
  atomic_store_explicit(&buf->trustlet_owned, false, memory_order_release);
}

// Driver side: wait until trustlet releases the buffer, return data length
static inline size_t driver_rx(struct buffer* buf) {
  while (atomic_load_explicit(&buf->trustlet_owned, memory_order_acquire)) {
    // spin wait
  }
  return buf->data_used;
}

// Driver side: set data length and give ownership to trustlet
static inline void driver_tx(struct buffer* buf, size_t len) {
  buf->data_used = len;
  atomic_store_explicit(&buf->trustlet_owned, true, memory_order_release);
}

#endif /* UTIL_H */
