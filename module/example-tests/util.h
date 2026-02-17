
#include <stddef.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <rte_tailq.h>

#define BUFFER_SIZE 1600
#define BURST_SIZE 1

#define CACHE_LINE_SIZE 64

#define SHARED_SIZE 4*4096
#define RING_SIZE 1024
#define MEMZONE_SIZE RTE_ALIGN(sizeof(struct rte_ring) + (ssize_t)RING_SIZE * sizeof(void*), RTE_CACHE_LINE_SIZE)
#define TAILQ_ENTRY_SIZE sizeof(struct rte_tailq_entry)


#ifndef DEBUG
#define DEBUG 0
#endif

#if DEBUG
#define debug
#else
#define debug if(0)
#endif

struct buffer {
  atomic_bool trustlet_owned;
  size_t data_used;
  char data[BUFFER_SIZE];
};

struct shm {
  struct buffer legacy_buffer; // TODO remove backwards compatibility
  // bool tailq_entry_buf_used;
  // bool memzone_buf_used;
  char tailq_entry_buf[TAILQ_ENTRY_SIZE] __attribute__((aligned(CACHE_LINE_SIZE)));
  char memzone_buf[MEMZONE_SIZE] __attribute__((aligned(CACHE_LINE_SIZE))); // TODO rename to what it actually contains
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

