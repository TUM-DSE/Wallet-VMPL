#include <stdlib.h>
#include <string.h>
#include <zygote.h>
#include <trustlet.h>
#include <monitor.h>
#include <time.h>
#include <stdint.h>
/* #include <sys/io.h> */

/* #define BENCHMARK_PORT 0xF4 */
/**/
/* static inline void call(unsigned short value){ */
/*     outb(value, BENCHMARK_PORT); */
/* } */

#define ITERATIONS 1

uint64_t get_time_ns(struct timespec* aux) {
    clock_gettime(CLOCK_MONOTONIC, aux);
    return aux->tv_sec * 1000000000ULL + aux->tv_nsec;
}

uint64_t get_time_cycles(unsigned int *aux) {
    return __builtin_ia32_rdtscp(aux);
}

void measure_ioctl() {
    struct timespec aux_;
    unsigned int aux;

    printf("Start benchmarking\n");
    uint64_t start_ns = get_time_ns(&aux_);
    uint64_t start_cycles = get_time_cycles(&aux);
    for (int i = 0; i < ITERATIONS; i++) {
        /* invoke_trustlet(NULL, "", 0); */
        /* int ret = ioctl(con, VMPL_WR, &aux); */
    }
    uint64_t end_cycles = get_time_cycles(&aux);
    uint64_t end_ns = get_time_ns(&aux_);

    printf("Time per invocation: %lu ns, %lu cycles\n",
           (end_ns - start_ns) / ITERATIONS,
           (end_cycles - start_cycles) / ITERATIONS);

    exit(0);
}

#define SHARED_SIZE (1024 * 1024)  // 1MB

int main() {
    struct timespec aux_;
    unsigned int aux;

    /* measure_ioctl(); */

    monitor_connect();

    printf("Create zygotes\n");
    int z = create_zygote("../libpal.so", "manifest_ipc_1", "../libsysdb.so");

    printf("Create trustlets\n");
    int t = create_trustlet(z, "./empty.py");

    printf("Invoke trustlet to initialize\n");
    invoke_trustlet(t, "1337", 5);

    // Test shared memory
    printf("=== Shared Memory Test ===\n");

    // Allocate page-aligned shared buffer
    char* shared = aligned_alloc(4096, SHARED_SIZE);
    if (!shared) {
        printf("Failed to allocate shared memory\n");
        return -1;
    }

    // Write initial data "AAAA"
    memset(shared, 'A', 4);
    shared[4] = '\0';
    printf("Before trustlet: shared = %.4s\n", shared);

    // Register shared memory with the trustlet
    if (!create_shared_memory(t, shared, SHARED_SIZE)) {
        printf("Failed to create shared memory\n");
        free(shared);
        return -1;
    }
    printf("Shared memory registered\n");

    // Invoke trustlet - it will modify the shared memory
    printf("Invoking trustlet to modify shared memory...\n");
    invoke_trustlet(t, "x", 0);

    // Verify the trustlet modified the shared buffer
    printf("After trustlet: shared = %.4s\n", shared);

    if (memcmp(shared, "BBBB", 4) == 0) {
        printf("SUCCESS: Shared memory was modified by trustlet!\n");
    } else {
        printf("FAILED: Shared memory was not modified as expected\n");
    }

    free(shared);

    // Original benchmark code
    printf("\n=== Benchmark ===\n");
    invoke_trustlet(t, "x", 0);

    printf("Start benchmarking\n");
    uint64_t sum = 0;
    char* ret = NULL;
    size_t ret_size = 5;
    uint64_t start_ns = get_time_ns(&aux_);
    uint64_t start_cycles = get_time_cycles(&aux);
    for (int i = 0; i < ITERATIONS; i++) {
        ret = invoke_trustlet(t, "1337", ret_size);
    }
    uint64_t end_cycles = get_time_cycles(&aux);
    uint64_t end_ns = get_time_ns(&aux_);

    ret[ret_size - 1] = '\0';
    printf("result: %s\n", ret);

    printf("Time per invocation: %lu ns, %lu cycles\n",
           (end_ns - start_ns) / ITERATIONS,
           (end_cycles - start_cycles) / ITERATIONS);

    return 0;
}
