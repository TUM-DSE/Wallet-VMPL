#define _GNU_SOURCE

#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <zygote.h>
#include <trustlet.h>
#include <monitor.h>
#include <time.h>
#include <stdint.h>
#include <sys/time.h>
#include <pthread.h>
#include <sched.h>
#include <unistd.h>
#include <stdio.h>
#include <errno.h>


void hexdump(const void *data, size_t size) {
    for (size_t i = 0; i < size; i++) printf("%02x ", ((unsigned char *)data)[i]);
    printf("\n");
}

// Threaded trustlet invocation
struct threaded_invoke_args {
  int trustlet;
  int cpu;
  char* input;
  uint64_t result_len;
  char* result;
};

struct threaded_invoke_handle {
  pthread_t thread;
  struct threaded_invoke_args args;
};

static void* threaded_invoke_fn(void* arg) {
  struct threaded_invoke_args* args = (struct threaded_invoke_args*)arg;

  // Set CPU affinity
  cpu_set_t cpuset;
  CPU_ZERO(&cpuset);
  CPU_SET(args->cpu, &cpuset);
  int ret = pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
  if (ret == EINVAL) {
    printf("Invalid CPU %d for affinity\n", args->cpu);
  } else if (ret != 0) {
    printf("Failed to set thread affinity: %s\n", strerror(ret));
  }

  // Invoke trustlet
  args->result = invoke_trustlet(args->trustlet, args->input, args->result_len);

  return NULL;
}

// Start a thread that invokes trustlet on specified CPU
static inline struct threaded_invoke_handle* threaded_invoke(int trustlet, int cpu, char* input, uint64_t result_len) {
  struct threaded_invoke_handle* handle = malloc(sizeof(struct threaded_invoke_handle));
  handle->args.trustlet = trustlet;
  handle->args.cpu = cpu;
  handle->args.input = input;
  handle->args.result_len = result_len;
  handle->args.result = NULL;

  pthread_create(&handle->thread, NULL, threaded_invoke_fn, &handle->args);
  return handle;
}

// Wait for threaded invoke to complete, return result
static inline char* threaded_join(struct threaded_invoke_handle* handle) {
  pthread_join(handle->thread, NULL);
  return handle->args.result;
}

// Free the handle (call after threaded_join)
static inline void threaded_free(struct threaded_invoke_handle* handle) {
  free(handle);
}
