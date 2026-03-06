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
#include <rte_mbuf.h>

#include "cpuid.c"
#include "../example-tests/util.h"
#include "../example-tests/shm_mempool.h"

#define PORT 0xF4
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000
#define DATA_SHARED 0x38000000000

#ifndef DATA_SIZE
#define DATA_SIZE 16
#endif

#ifndef PER_VNFLET_WORKLOAD_NS
#define PER_VNFLET_WORKLOAD_NS 0
#endif

#define println(...) do { fprintf(stdout, __VA_ARGS__); fflush(stdout); } while(0)
#define READ_ONCE(x) (*(volatile typeof(x) *)&(x))

void hexdump(const void *data, size_t size) {
    for (size_t i = 0; i < size; i++) printf("%02x ", ((unsigned char *)data)[i]);
    println("");
}

static void* next_tailq_buf = NULL;
static void* next_memhdr_buf = NULL;

// when statically linking DPDK, we make DPDK use these wrappers via --wrap compile flag
void *__wrap_rte_zmalloc(const char *type, size_t size, unsigned align) {
    if (size == TAILQ_ENTRY_SIZE) {
        return next_tailq_buf;
    }
    if (size == sizeof(struct rte_mempool_memhdr)) {
        return next_memhdr_buf;
    }
    return NULL;
    /* return calloc(1, size); */
}

static void* next_alloc_buffer = NULL;

const struct rte_memzone *__wrap_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align) {
    println("rte_memzone_reserve_aligned: name=%s, len=%lu, socket_id=%d, flags=%u, align=%u", name, len, socket_id, flags, align);
    struct rte_memzone *mz = calloc(1, sizeof(struct rte_memzone));
    mz->len = len;
    mz->socket_id = socket_id;
    mz->flags = flags;
    if (len == RING_BUF_SIZE || len == POOL_PRIV_SIZE) { // sanity check. These are the only two allocations we are expecting
        mz->addr = next_alloc_buffer;
    }
    /* mz->addr = malloc(len); */
    if (!mz->addr) {
        println("Failed to allocate memory for memzone");
    }
    return mz;
}

// used for struct rte_pktmbuf_pool_private
const struct rte_memzone *__wrap_rte_memzone_reserve(const char *name,
			size_t len, int socket_id,
			unsigned flags) {
	assert(((len + RTE_MEMPOOL_ALIGN_MASK) & (~RTE_MEMPOOL_ALIGN_MASK)) == POOL_PRIV_SIZE);
	return __wrap_rte_memzone_reserve_aligned(name, len, socket_id, flags, -1);
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
    if (nsecs == 0) return;

    uint64_t start = clock_monotonic_get();
    uint64_t end = start + nsecs;
    debug println("delay: start=%lu, end=%lu, waiting for %lu ns", start, end, nsecs);
    while (1) {
        uint64_t now = clock_monotonic_get();
        if (now >= end) {
            debug println("delay: done, slept %lu ns", now - start);
            break;
        }
    }
}

/// Creates a ring into data_shared->ingress and ->egress
bool ring_pair_create(struct shm* data_shared) {
    next_tailq_buf = data_shared->tailq_entry_buf;
    next_alloc_buffer = data_shared->ingress.buf; // rte_ring_create will create itself in this buffer
    struct rte_ring *ring = rte_ring_create("test_ring", RING_SIZE, SOCKET_ID_ANY,
                                             RING_F_SP_ENQ | RING_F_SC_DEQ);
    next_tailq_buf = NULL;
    next_alloc_buffer = NULL;

    if (!ring) {
        println("Failed to create ingress ring");
        return false;
    }
    println("Ingress ring created: %s, count=%u", ring->name, rte_ring_count(ring));

    next_tailq_buf = data_shared->tailq_entry_buf; // we can reuse the same buffer for this new tailq, trust me bro (the entry will be the same and is not really relevant anyways)
    next_alloc_buffer = data_shared->egress.buf; // rte_ring_create will create itself in this buffer
    ring = rte_ring_create("test_ring", RING_SIZE, SOCKET_ID_ANY,
                                             RING_F_SP_ENQ | RING_F_SC_DEQ);
    next_tailq_buf = NULL;
    next_alloc_buffer = NULL;

    if (!ring) {
        println("Failed to create exgress ring");
        return false;
    }
    println("Egress ring created: %s, count=%u", ring->name, rte_ring_count(ring));

    return true;
}

void main_shm(char mode, struct shm *data_shared_previous, struct shm *data_shared_next) {
    struct shm* buf = data_shared_previous;
    size_t buf_used = 0;
    size_t num_deq = 0, num_enq = 0, total_rx = 0, total_tx = 0;
    void *deq_objs[BURST_SIZE];
    void *enq_objs[BURST_SIZE];
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
    if (!ring_pair_create(data_shared_previous))
        return;

    // Create mbuf pool backed by shared memory
    struct rte_mempool *pool1 = data_shared_previous->mbuf_pool;
    if (mode != MODE_FIRST_NODE) { // first node pool allocated by driver
        println("create_shm_mbuf_pool(%s, %p)", "VNFlet_MBUF_POOL", data_shared_previous);
        next_alloc_buffer = data_shared_previous->pool_priv; // TODO:
        next_tailq_buf = data_shared_previous->tailq_entry_buf; // we can reuse the same buffer for this new tailq, trust me bro (the entry will be the same and is not really relevant anyways)
        next_memhdr_buf = (void*)&data_shared_previous->pool_memhdr;
        data_shared_previous->mbuf_pool = create_shm_mbuf_pool("VNFlet_MBUF_POOL", data_shared_previous);
        next_alloc_buffer = NULL;
        next_tailq_buf = NULL;
        next_memhdr_buf = NULL;
        pool1 = data_shared_previous->mbuf_pool;
        if (!pool1) {
            printf("Failed to create shm mbuf pool\n");
            return;
        }
        printf("Mbuf pool %p created with %u objects\n", pool1, pool1->populated_size);

        data_shared_previous->keep_running = true;
    }
    assert(pool1 != NULL && "pool1 need to be allocated by driver");


    // Initialize DPDK ring
    struct rte_mempool *pool2 = data_shared_next->mbuf_pool;
    if (mode == MODE_LAST_NODE) { // last node pool has no next to allocate the rings
        if (!ring_pair_create(data_shared_next))
            return;

        println("create_shm_mbuf_pool(%s, %p)", "VNFlet_MBUF_POOL", data_shared_next);
        next_alloc_buffer = data_shared_next->pool_priv; // TODO:
        next_tailq_buf = data_shared_next->tailq_entry_buf; // we can reuse the same buffer for this new tailq, trust me bro (the entry will be the same and is not really relevant anyways)
        next_memhdr_buf = (void*)&data_shared_next->pool_memhdr;
        data_shared_next->mbuf_pool = create_shm_mbuf_pool("VNFlet_MBUF_POOL", data_shared_next);
        next_alloc_buffer = NULL;
        next_tailq_buf = NULL;
        next_memhdr_buf = NULL;
        pool2 = data_shared_next->mbuf_pool;
        if (!pool2) {
            printf("Failed to create shm mbuf pool\n");
            return;
        }
        printf("Mbuf pool %p created with %u objects\n", pool2, pool2->populated_size);
    }

    trustlet_exit();

    /* println("Waiting for pool2 to be allocated by next VNFlet..."); */
    /* while (READ_ONCE(data_shared_next->mbuf_pool) == NULL) {} */
    pool2 = data_shared_next->mbuf_pool;
    // data_shared_next mbuf pool is always allocated by the next VNFlet (or the driver in case of MODE_LAST_NODE)
    /* if (mode != MODE_LAST_NODE) { // last node pool allocated by driver */
    /*     // Create mbuf pool backed by shared memory */
    /*     data_shared_next->mbuf_pool = create_shm_mbuf_pool(data_shared_next); */
    /*     pool2 = data_shared_next->mbuf_pool; */
    /*     if (!pool2) { */
    /*         printf("Failed to create shm mbuf pool\n"); */
    /*         return; */
    /*     } */
    /*     printf("Mbuf pool created with %u objects\n", pool2->populated_size); */
    /* } */
    printf("Require pool %p\n", pool2);
    assert(pool2 != NULL && "pool2 need to be allocated by someone else");

    uint64_t duration_ns = 15ULL * 1000000000ULL; // 15 seconds
    uint64_t check_interval = 1e6;
    uint64_t start_time = clock_monotonic_get();
    uint64_t end_time = start_time + duration_ns;
    uint64_t iterations = 0;
    char local_bufs[BURST_SIZE][SHM_POOL_DATA_ROOM];
    size_t local_buf_lens[BURST_SIZE];

    while (likely(atomic_load(&data_shared_previous->keep_running))) {
        println("p1");
        iterations++;
        delay(1*1e9);
        /* buf_used = trustlet_rx(buf); */
        /* buf->data[3] += 1; */
        /* trustlet_tx(buf, buf_used); */

        println("p2");
        num_deq = rte_ring_sc_dequeue_burst(&data_shared_previous->ingress.ring, deq_objs, BURST_SIZE, NULL); // pool1 bufs
        println("%lu = rte_ring_sc_dequeue_burst(%p, ...)", num_deq, &data_shared_previous->ingress.ring);

        if(num_deq == 0) {
            /* vnflet_stats[vnfletId].dequeue_failures++; */
            continue;
        } else {
            total_rx += num_deq;
            debug println("Dequeued %lu objects from ring. First: %p", num_deq, deq_objs[0]);

            // pkts -> local buffer
            for (size_t i = 0; i < num_deq; i++) {
                struct rte_mbuf *m = (struct rte_mbuf *)deq_objs[i];
                uint16_t len = m->data_len;
                local_buf_lens[i] = len;
                memcpy(local_bufs[i], rte_pktmbuf_mtod(m, void *), len);
            }

            // return empty buffer to previous (our mempool is not atomic, so we have to pass back atomically)
            size_t nb_returned = rte_ring_sp_enqueue_bulk(&data_shared_previous->egress.ring, (void**)(&(deq_objs[0])), num_deq, NULL);
            if (nb_returned != num_deq) {
                println("Failed to return all buffers to previous VNFlet. Is pool bigger than the ring pair combined?");
                return;
            }

            delay(PER_VNFLET_WORKLOAD_NS); // simulate per-packet processing

            int ret = rte_pktmbuf_alloc_bulk(pool2, (struct rte_mbuf **)enq_objs, num_deq);
            if (ret != 0) {
                // maybe next VNFlet is overloaded?
                // drop num_deq packets
            } else {
                // local buffer -> pkts
                for (size_t i = 0; i < num_deq; i++) {
                    struct rte_mbuf *m = (struct rte_mbuf *)enq_objs[i];
                    uint16_t len = local_buf_lens[i];
                    m->data_len = len;
                    m->pkt_len = len;
                    memcpy(rte_pktmbuf_mtod(m, void *), local_bufs[i], len);
                }

                // pass buffers to next VNFlet
                num_enq = rte_ring_sp_enqueue_bulk(&data_shared_next->ingress.ring, enq_objs, num_deq, NULL);
                if (num_enq == 0)
                    rte_pktmbuf_free_bulk((struct rte_mbuf **)enq_objs, num_deq);
                else {
                    total_tx += num_enq;
                    debug println("Enqueued %lu objects to ring.", num_enq);
                }

                num_deq = rte_ring_sc_dequeue_burst(&data_shared_next->egress.ring, deq_objs, BURST_SIZE, NULL);
                if (num_deq > 0) {
                    for (size_t i = 0; i < num_deq; i++) {
                        rte_pktmbuf_free(deq_objs[i]);
                    }
                }

            }


        }



        // TODO: copy mbufs to local mem, send back empty buffer, allocate mbuf from pool2, copy data to it, sent it to data_shared_next ring, receive empty mbufs

        /* num_enq = rte_ring_sp_enqueue_bulk(&buf->egress.ring, (void**)(&(deq_objs[0])), num_deq, NULL); */
        /* total_tx += num_enq; */
        /* debug println("Enqueued %lu objects to ring.", num_enq); */

        /* ndelay(workload_cycles); */

        /* num_enq = rte_ring_sp_enqueue_bulk(TODO, deq_objs, num_deq, NULL); */
    }
    atomic_store(&data_shared_next->keep_running, false); // signal next trustlet to stop as well
    uint64_t elapsed_ns = clock_monotonic_get() - start_time;
    println("Finished %lu iterations in %.1f s, total_rx=%lu", iterations, elapsed_ns / 1e9, total_rx);
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
    println("Trustlet main at %p", main);

    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    finalize_zygote();
    int type = 0;

    println("malloc start");
    char* buf = malloc(2097152);
    println("malloc end");

    println("main exit enter");
    trustlet_exit();
    println("main exit exit");

    struct trustlet_configuration *config = (struct trustlet_configuration *)input;

    if(config->mode[0] == MODE_FIRST_NODE || config->mode[0] == MODE_MIDDLE_NODE || config->mode[0] == MODE_LAST_NODE){
        main_shm(config->mode[0], config->shm_addr_previous, config->shm_addr_next);
    } else if(config->mode[0] == 'x'){
        bool suppress_output = false;
        main_default(suppress_output);
    } else {
        bool suppress_output = true;
        main_default(suppress_output);
    }
}
