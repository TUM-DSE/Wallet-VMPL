#include <stdlib.h>
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

int main() {
    struct timespec aux_;
    unsigned int aux;

    /* measure_ioctl(); */



    /* if (ioperm(BENCHMARK_PORT, 1, 1)) { */
    /*     printf("Failed to get access to the benchmark port\n"); */
    /*     return -1; */
    /* } */
    /* call(101); */
    monitor_connect();
    /* call(102); */
    /* call(103); */
    printf("Create zygotes\n");
    int z = create_zygote("../libpal.so", "manifest_ipc_1", "../libsysdb.so");
    /* call(104); */
    /* call(105); */
    printf("Create trustlets\n");
    int t = create_trustlet(z, "./empty.py");
    /* call(106); */
    /* call(107); */
    printf("Invoke trustlests to initialize\n");
    invoke_trustlet(t, "1337", 5);
    /* call(108); */

    /* printf("Chreate chain\n"); */
    // create_channel
    printf("Invoke chain to initialize\n");
    /* invoke_trustlet(t, "a", 0); */
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

    printf("Ioctl time per invocation: %lu cycles\n",
           sum / ITERATIONS);
    printf("Time per invocation: %lu ns, %lu cycles\n",
           (end_ns - start_ns) / ITERATIONS,
           (end_cycles - start_cycles) / ITERATIONS);
    
}
