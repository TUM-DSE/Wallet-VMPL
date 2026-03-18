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
  bool placeholder;
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
  // Linear accesses
  // uint64_t start = rte_rand_max(WORKLOAD_STATE_SIZE_B / sizeof(uint64_t));
  uint64_t start = rand() % (WORKLOAD_STATE_SIZE_B / sizeof(uint64_t));
  for (int i = 0; i < WORKLOAD_ACCESSES_B * nr_packets / sizeof(uint64_t); i++) {
    uint64_t pos = (start + i) % (WORKLOAD_STATE_SIZE_B / sizeof(uint64_t));
    volatile uint64_t x = self->array[pos];
  }
  // Random accesses (prng bottlenecked)
  // for (int i = 0; i < WORKLOAD_ACCESSES_B / sizeof(uint64_t); i++) {
  //   uint64_t pos = rte_rand_max(WORKLOAD_STATE_SIZE_B / sizeof(uint64_t));
  //   volatile uint64_t x = self->array[pos];
  // }

#endif
}
