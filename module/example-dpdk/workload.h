#include <stdlib.h>
#include <string.h>

#ifndef WORKLOAD_STATE_SIZE_B
#define WORKLOAD_STATE_SIZE_B 300 * 1024 * 1024 // MB
#endif

#ifndef WORKLOAD_ACCESSES_B
#define WORKLOAD_ACCESSES_B 0
#endif

#if WORKLOAD_ACCESSES_B == 0
#define WORKLOAD_DISABLE
#endif
#if WORKLOAD_STATE_SIZE_B == 0
#define WORKLOAD_DISABLE
#endif

#define println(...) do { fprintf(stdout, __VA_ARGS__); fflush(stdout); } while(0)

struct workload {
  uint64_t placeholder;
  volatile uint64_t array[];
};

static struct workload* workload_alloc() {
#ifndef WORKLOAD_DISABLE
  struct workload* w = (struct workload*) malloc(sizeof(struct workload) + WORKLOAD_STATE_SIZE_B);
  memset((void*)w, -1, sizeof(struct workload) + WORKLOAD_STATE_SIZE_B);
  println("Srand...");
  // rte_srand(12345);
  srand(12345);
  println("... srand");
  return w;
#else
  return NULL;
#endif
}

inline static void artificial_workload(struct workload* self, size_t nr_packets) {
#ifndef WORKLOAD_DISABLE
  const size_t array_len = WORKLOAD_STATE_SIZE_B / sizeof(uint64_t);
  uint64_t r = rand();
  for (int i = 0; i < WORKLOAD_ACCESSES_B * nr_packets / sizeof(uint64_t); i++) {
    uint64_t pos = r % array_len;
    uint64_t data = self->array[pos];
    r = data ^ (r << 24 ^ r << 16 ^ r << 8 ^ r >> 16); // poor mans new random number: fast, but sufficient to prevent prefetching of subsequent accesses
  }
  // Prevent the compiler from optimizing away the chain
  *(volatile uint64_t*)&self->placeholder = r;
  // Random accesses (prng bottlenecked)
  // for (int i = 0; i < WORKLOAD_ACCESSES_B / sizeof(uint64_t); i++) {
  //   uint64_t pos = rte_rand_max(WORKLOAD_STATE_SIZE_B / sizeof(uint64_t));
  //   volatile uint64_t x = self->array[pos];
  // }

#endif
}
