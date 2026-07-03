#ifndef UTIL_H
#define UTIL_H

#include <stddef.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

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

// Number of rte_mbuf objects in the shared mempool. Was 2*RING_SIZE (so both
// of a channel's rings can be full without draining the pool), reduced to
// 1536 when the data room grew to 2048 for TSO: the 4MB SHARED_SIZE region
// fits at most ~1745 of the bigger elements (align64(objhdr + rte_mbuf +
// 2176) = ~2368B each; pool_buf 1536*2368 = ~3.6MB + rings/stack/priv).
// Exhaustion under deep TSO bursts (a 64KB frame consumes ~32 mbufs) is
// expected and SURVIVABLE: F-Stack's tcp_output gets a graceful ENOBUFS
// (cwnd collapse + retry) since the ff-veth-transmit-positive-errno patch,
// and the driver counts dropped RX copies in drop_rx_copy. Page-boundary
// skips in rte_mempool_populate_iova put the populated count ~10% below
// this figure.
#define SHM_POOL_SIZE 1536
// Packet data buffer size per mbuf. MUST be >= RTE_PKTMBUF_HEADROOM +
// RTE_MBUF_DEFAULT_DATAROOM (2048): F-Stack's ff_dpdk_if_send chops TSO
// super-frames into segments of exactly RTE_MBUF_DEFAULT_DATAROOM bytes
// regardless of the pool's actual data room (a smaller room = heap overrun).
#define SHM_POOL_DATA_ROOM (RTE_PKTMBUF_HEADROOM + 2048)
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
  // Spinlock guarding top/objs. This mbuf pool lives in shared memory and is
  // alloc(pop)/free(push)ed CONCURRENTLY by the guest driver (VMPL3) and the
  // VNFlet's F-Stack (VMPL2) on different cores. The original code used a plain
  // non-atomic `top++`/`--top`, so two concurrent pops could read the same top
  // and hand out the SAME mbuf twice (double allocation); the two owners then
  // write different packets into one buffer -> a buffer carries a valid checksum
  // but the wrong/stale packet -> intermittent TCP loss/desync with ZERO ring/
  // pool drop counters. This lock serializes the stack across VMPLs. Disable with
  // -DSHM_STACK_NO_LOCK to reproduce the racy behaviour for A/B testing.
  atomic_flag lock;
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
#define MODE_IOMGR_LOADGEN '5'
  char mode[1];
  void* shm_addr_previous; // previous VNFlets or driver
  void* shm_addr_next; // next VNFlet or driver
};

// written by the iomgr loadgen (MODE_IOMGR_LOADGEN), read by the driver
struct loadgen_results {
  uint64_t packets;
  uint64_t elapsed_ns;
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

  struct loadgen_results loadgen_results;
};

// The whole channel struct (incl. pool_buf) must fit the mapped region;
// catches SHM_POOL_SIZE/DATA_ROOM combinations that overflow SHARED_SIZE.
_Static_assert(sizeof(struct shm) <= SHARED_SIZE, "struct shm exceeds SHARED_SIZE");

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
