#include <stdio.h>
#include <sys/io.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include <time.h>

#include <rte_eal.h>
#include <rte_errno.h>
#include <rte_ring.h>
#include <rte_memzone.h>

#include "cpuid.c"
#include "util.h"

#define PORT 0xF4
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000
#define DATA_SHARED 0x38000000000
#define DATA_SIZE 16

#define println(...) do { fprintf(stdout, __VA_ARGS__); fflush(stdout); } while(0)

void hexdump(const void *data, size_t size) {
    for (size_t i = 0; i < size; i++) printf("%02x ", ((unsigned char *)data)[i]);
    println("");
}

// when statically linking DPDK, we make DPDK use these wrappers via --wrap compile flag
void *__wrap_rte_zmalloc(const char *type, size_t size, unsigned align) {
    struct shm* shm = (struct shm*)DATA_SHARED;
    if (size == TAILQ_ENTRY_SIZE) {
        return shm->tailq_entry_buf;
    }
    return NULL;
    /* return calloc(1, size); */
}

const struct rte_memzone *__wrap_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align) {
    println("rte_memzone_reserve_aligned: name=%s, len=%lu, socket_id=%d, flags=%u, align=%u", name, len, socket_id, flags, align);
    struct rte_memzone *mz = calloc(1, sizeof(struct rte_memzone));
    mz->len = len;
    mz->socket_id = socket_id;
    mz->flags = flags;
    if (len == MEMZONE_SIZE) {
        mz->addr = ((struct shm*)DATA_SHARED)->memzone_buf;
    }
    /* mz->addr = malloc(len); */
    if (!mz->addr) {
        println("Failed to allocate memory for memzone");
    }
    return mz;
}


// CPU frequency in GHz - used to correct clock_gettime which returns TSC cycles
#define CPU_GHZ 2.0

// Returns monotonic time in nanoseconds
// Note: clock_gettime returns TSC cycles misinterpreted as usec, then converted to nsec
// Effective value is cycles * 1000, so divide by (CPU_GHZ * 1000) to get real nsec
static inline uint64_t clock_monotonic_get(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (ts.tv_sec * 1000000000ULL + ts.tv_nsec) / (CPU_GHZ * 1000);
}

// build our own delay, because gramine's sleep is unimplemented
void delay(uint64_t nsecs) {
    uint64_t start = clock_monotonic_get();
    uint64_t end = start + nsecs;
    println("delay: start=%lu, end=%lu, waiting for %lu ns", start, end, nsecs);
    while (1) {
        uint64_t now = clock_monotonic_get();
        if (now >= end) {
            println("delay: done, slept %lu ns", now - start);
            break;
        }
    }
}

void main_shm() {
    char* shared = (char*)DATA_SHARED;
    struct shm* buf = (struct shm*)shared; // TODO
    size_t buf_used = 0;
    size_t num_deq, num_enq, total_rx = 0;
    void *deq_objs[BURST_SIZE];
    delay(1); // warm up CoW triggered by delay

    // Initialize DPDK EAL with --no-huge for environments without hugepages
    println("Initializing EAL...");
    /* char *eal_args[] = {"slick_vnflet", "--no-huge"}; */
    /* int eal_argc = sizeof(eal_args) / sizeof(eal_args[0]); */
    /* int ret = rte_eal_init(eal_argc, eal_args); */
    /* if (ret < 0) { */
    /*     println("Failed to initialize EAL: %s\n", rte_strerror(rte_errno)); */
    /*     return -1; */
    /* } */

    // Initialize DPDK ring
    struct rte_ring *ring = rte_ring_create("test_ring", RING_SIZE, SOCKET_ID_ANY,
                                             RING_F_SP_ENQ | RING_F_SC_DEQ);
    if (!ring) {
        println("Failed to create ring");
        return -1;
    }
    println("Ring created: %s, count=%u", ring->name, rte_ring_count(ring));
    trustlet_exit();



    int iterations = 1e9;
    for (int iter = 0; iter < iterations; iter++) {
        /* delay(10*1e9); // Sleep for, e.g., 65 seconds to see if kernel stall detection will kill us */
        /* buf_used = trustlet_rx(buf); */
        /* buf->data[3] += 1; */
        /* trustlet_tx(buf, buf_used); */


        num_deq = rte_ring_sc_dequeue_burst(buf->memzone_buf, deq_objs, BURST_SIZE, NULL);

        if(num_deq == 0) {
            /* vnflet_stats[vnfletId].dequeue_failures++; */
            continue;
        }

        total_rx += num_deq;
        println("Dequeued %lu objects from ring. First: %p", num_deq, deq_objs[0]);

        /* ndelay(workload_cycles); */

        /* num_enq = rte_ring_sp_enqueue_bulk(TODO, deq_objs, num_deq, NULL); */


    }
    println("Finished %d iterations, total_rx=%lu", iterations, total_rx);
    delay(1*1e9); // try to mitigate print interleaving
    notify_monitor();
}

void main_default(bool suppress_output) {
    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    trustlet_exit();

    while (1) {
        memcpy(output, input, DATA_SIZE);

        if (suppress_output) {
            output[1] += 1;
            printf("Trustlet processed: ");
            hexdump(output, DATA_SIZE);
            trustlet_exit();
        } else {
            output[2] += 1;
            printf("Trustlet processed: ");
            hexdump(output, DATA_SIZE);
            notify_monitor();
        }
    }
}

int main(int argc, char** argv) {

    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    finalize_zygote();
    int type = 0;
    int data_size = 64 * 1024;

    println("malloc start");
    char* buf = malloc(2097152);
    println("malloc end");

    println("main exit enter");
    trustlet_exit();
    println("main exit exit");

    if(input[0] == 's'){
        main_shm();
    } else if(input[0] == 'x'){
        bool suppress_output = false;
        main_default(suppress_output);
    } else {
        bool suppress_output = true;
        main_default(suppress_output);
    }
}
