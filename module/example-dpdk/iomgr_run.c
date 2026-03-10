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
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#include <rte_eal.h>
#include <rte_errno.h>
#include <rte_ring.h>
#include <rte_mbuf.h>

#include "../include/cpuid.h"
#include "../example-tests/util.h"
#include "../example-tests/util_run.h"
#include "../example-tests/shm_mempool.h"
#include "cvmio.h"

// like test12, but with real CVM IO

#define DATA_SIZE PACKET_SIZE

#ifndef CHAINING
#define CHAINING 2
#endif

/* static void* DATA_SHARED = NULL; */
static __thread bool use_shm_alloc = false;

#define WITH_SHM_ALLOC(expr) ({ \
    use_shm_alloc = true; \
    __typeof__(expr) _result = (expr); \
    use_shm_alloc = false; \
    _result; \
})


// when statically linking DPDK, we make DPDK use these wrappers via --wrap compile flag
// extern void *__real_rte_zmalloc(const char *type, size_t size, unsigned align);
// void *__wrap_rte_zmalloc(const char *type, size_t size, unsigned align) {
//     if (use_shm_alloc) {
//         struct shm* shm = (struct shm*)DATA_SHARED;
//         if (size == TAILQ_ENTRY_SIZE) {
//             return shm->tailq_entry_buf;
//         }
//         return NULL;
//     } else {
//         return __real_rte_zmalloc(type, size, align);
//     }
//     /* return calloc(1, size); */
// }
//
// extern const struct rte_memzone *__real_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align);
// const struct rte_memzone *__wrap_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align) {
//     if (use_shm_alloc) {
//         printf("rte_memzone_reserve_aligned: name=%s, len=%lu, socket_id=%d, flags=%u, align=%u\n", name, len, socket_id, flags, align);
//         struct rte_memzone *mz = calloc(1, sizeof(struct rte_memzone));
//         mz->len = len;
//         mz->socket_id = socket_id;
//         mz->flags = flags;
//         if (len == RING_BUF_SIZE) {
//             mz->addr = ((struct shm*)DATA_SHARED)->ingress.buf;
//         }
//         /* mz->addr = malloc(len); */
//         if (!mz->addr) {
//             printf("Failed to allocate memory for memzone\n");
//         }
//         return mz;
//     } else {
//         return __real_rte_memzone_reserve_aligned(name, len, socket_id, flags, align);
//     }
// }


int main(int argc, char *argv[]) {
    // with wallet.Wallet() as w:
    monitor_connect();

    // Initialize DPDK EAL with --no-huge for environments without hugepages
    char *eal_args[] = {"noiomgr_run", "--no-huge", "-l", "0", "--iova-mode=pa"};
    int eal_argc = sizeof(eal_args) / sizeof(eal_args[0]);
    int ret = rte_eal_init(eal_argc, eal_args);
    if (ret < 0) {
        printf("Failed to initialize EAL: %s\n", rte_strerror(rte_errno));
        return -1;
    }

    // Restore full CPU affinity (EAL restricts it to -l cores)
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    for (int i = 0; i < sysconf(_SC_NPROCESSORS_ONLN); i++)
        CPU_SET(i, &cpuset);
    sched_setaffinity(0, sizeof(cpuset), &cpuset);

    struct rte_mempool *cvmio_pool = cvmio_init();
    uint16_t port = rte_eth_find_next(0);

    // Ring already initialized. We just cast the shm buffer to a ring.
    // // Initialize DPDK ring
    // // TODO create wrappers to also allocate this ring on shm
    // struct rte_ring *ring = WITH_SHM_ALLOC(rte_ring_create("test_ring", 1024, SOCKET_ID_ANY, RING_F_SP_ENQ | RING_F_SC_DEQ));
    // if (!ring) {
    //     printf("Failed to create ring\n");
    //     return -1;
    // }
    // printf("Ring created: %s, count=%u\n", ring->name, rte_ring_count(ring));


    int input_size = 16;

    int chain_len = CHAINING;
    int chains[] = {CHAINING};
    int chains_len = 1;

    int iterations = 1e9;

    int zygotes[2];
    int trustlets[2];
    int iomgr_zygote;
    int iomgr_trustlet;
    struct threaded_invoke_handle* handles[2];
    struct threaded_invoke_handle* iomgr_handle;

    // for i in range(chain_len):
    //     zygotes.append(w.create_zygote("../libpal.so", "test4_manifest", "../libsysdb.so"))
    for (int i = 0; i < chain_len; i++) {
        zygotes[i] = create_zygote("../libpal.so", "iomgr_manifest", "../libsysdb.so");
    }
    iomgr_zygote = create_zygote("../libpal.so", "iomgr_manifest", "../libsysdb.so");

    // for i in range(chain_len):
    //     trustlets.append(zygotes[i].create_trustlet("./empty.py"))
    for (int i = 0; i < chain_len; i++) {
        trustlets[i] = create_trustlet(zygotes[i], "./empty.py");
    }
    iomgr_trustlet = create_trustlet(iomgr_zygote, "./empty.py");

    // Allocate shared memory at the same VA the trustlet uses (DATA_SHARED),
    // so pointers within shm (e.g. mbuf buf_addr) are valid in both address spaces.
    void *target_addr = (void *)CHANNEL_ADDR(0);
    struct shm* shared = (struct shm*)mmap(target_addr, SHARED_SIZE,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
        -1, 0);
    if (shared == MAP_FAILED) {
        printf("mmap at %p failed: %s\n", target_addr, strerror(errno));
        return -1;
    }
    if (SHARED_SIZE < sizeof(struct shm)) {
        printf("Shared memory size is too small (is: %d, need: %d)\n", SHARED_SIZE, (int)sizeof(struct shm));
        return -1;
    }
    memset(shared, 0, SHARED_SIZE);
    shared->legacy_buffer.data[0] = 'I';
    shared->keep_running = true;
    for (int i = 0; i < chain_len; i++) {
        if (!create_shared_memory(trustlets[i], shared, SHARED_SIZE)) {
            printf("Failed to create shared memory to trustlet %d\n", i);
            return -1;
        }
    }
    if (!create_shared_memory(iomgr_trustlet, shared, SHARED_SIZE)) {
        printf("Failed to create shared memory\n");
        return -1;
    }
    printf("Shared memory registered\n");

    // Create mbuf pool backed by shared memory
    printf("create_shm_mbuf_pool(%s, %p)\n", "SHM1_MBUF_POOL", shared);
    struct rte_mempool *pool = create_shm_mbuf_pool("SHM1_MBUF_POOL", shared);
    if (!pool) {
        printf("Failed to create shm mbuf pool\n");
        return -1;
    }

    shared->mbuf_pool = pool;
    printf("Mbuf pool created with %u objects\n", pool->populated_size);

    // allocate second shm
    target_addr = (void *)CHANNEL_ADDR(1);
    struct shm* shared2 = (struct shm*)mmap(target_addr, SHARED_SIZE,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
        -1, 0);
    if (shared2 == MAP_FAILED) {
        printf("mmap at %p failed: %s\n", target_addr, strerror(errno));
        return -1;
    }
    memset(shared2, 0, SHARED_SIZE);
    shared2->legacy_buffer.data[0] = 'I';
    shared2->keep_running = true;
    if (!create_shared_memory(iomgr_trustlet, shared2, SHARED_SIZE)) {
        printf("Failed to create shared memory\n");
        return -1;
    }

    // We do the following in the first trustlet now, because we are missing the allocator wrappers here that are present in the trustlet. I dont want to add them here, because it would pollute our cvmio external setup maybe?
    // // Create mbuf pool backed by shared memory
    // printf("create_shm_mbuf_pool(%s, %p)\n", "SHM2_MBUF_POOL", shared2);
    // struct rte_mempool *pool2 = create_shm_mbuf_pool("SHM2_MBUF_POOL", shared2);
    // if (!pool2) {
    //     printf("Failed to create shm mbuf pool\n");
    //     return -1;
    // }

    // shared2->mbuf_pool = pool2;
    // printf("Mbuf pool created with %u objects\n", pool2->populated_size);

    // input_data = b"a" * (input_size - 1) + b"\00"
    char input_data[16];
    memset(input_data, 'a', input_size - 1);
    input_data[input_size - 1] = '\0';

    // for t in trustlets:
    //     t.invoke_trustlet(input_data, len(input_data))
    for (int t = 0; t < chain_len; t++) {
        printf("152:invoke_trustlet()");
        invoke_trustlet(trustlets[t], input_data, input_size);
    }
    invoke_trustlet(iomgr_trustlet, input_data, input_size);

    // for i in chains:
    for (int idx = 0; idx < chains_len; idx++) {
        int i = chains[idx];

        // #Create chains
        // for c in range(chained,i - 1):
        //     trustlets[c].create_channel(trustlets[c+1])
        for (int c = 0; c < i; c++) {
            // create_channel(trustlets[c], trustlets[c+1]);
            create_channel_at(iomgr_trustlet, trustlets[c], (uint64_t)CHANNEL_ADDR(2+c), SHARED_SIZE);
        }

        // Configure first-in-chain trustlet
        struct trustlet_configuration config;
        config.mode[0] = MODE_MIDDLE_NODE;
        config.shm_addr_previous = CHANNEL_ADDR(2);
        config.shm_addr_next = CHANNEL_ADDR(0);
        invoke_trustlet_bin(trustlets[0], &config, sizeof(config), 0);

        // #Setup Trustlets
        // for t in range(i - 1):
        //     trustlets[t].invoke_trustlet(b"a", 0)
        printf("185:invoke_trustlet()");
        for (int t = 1; t < i - 1; t++) {
            // Transfer nodes (input->output)
            config.mode[0] = MODE_MIDDLE_NODE;
            config.shm_addr_previous = CHANNEL_ADDR(2+t);
            config.shm_addr_next = CHANNEL_ADDR(0);
            invoke_trustlet_bin(trustlets[t], &config, sizeof(config), 0);
        }
        // trustlets[i - 1].invoke_trustlet(b"s", 0)
        // End node - use shm mode
        config.mode[0] = MODE_LAST_NODE;
        config.shm_addr_previous = CHANNEL_ADDR(i+1);
        config.shm_addr_next = CHANNEL_ADDR(0);
        invoke_trustlet_bin(trustlets[i - 1], &config, sizeof(config), 0);

        // Setup IoMgr
        config.mode[0] = MODE_IOMGR_NODE;
        config.shm_addr_previous = CHANNEL_ADDR(0);
        config.shm_addr_next = CHANNEL_ADDR(1);
        invoke_trustlet_bin(iomgr_trustlet, &config, sizeof(config), 0);

        // start long-running trustlet
        /* invoke_trustlet(trustlets[1], "s", 0); */
        printf("Starting trustlet 0 on core 1\n");
        handles[0] = threaded_invoke(trustlets[0], 1, "", 0);
        for (int t = 1; t < i - 1; t++) {
            printf("Starting trustlet %d on core %d\n", t, t+1);
            handles[t] = threaded_invoke(trustlets[t], t + 1, "", 0);
        }
            printf("Starting trustlet %d on core %d\n", i - 1, i - 1 + 1);
        handles[i-1] = threaded_invoke(trustlets[i - 1], i - 1 + 1, "", 0);
            printf("Starting IoMgr on core %d\n", i - 1 + 1);
        iomgr_handle = threaded_invoke(iomgr_trustlet, i - 1 + 2, "", 0);

        sleep(120); // give trustlet time to start TODO: if truslets need more than this to init queues and pools, we may be cooked

        size_t enq_num = 0, num_enqed = 0, deq_num = 0, num_deqed = 0;
        void *enq_objs[BURST_SIZE];
        void *deq_objs[BURST_SIZE];
        struct rte_mbuf *bufs[BURST_SIZE];


        printf("Starting %d iterations...\n", iterations);
        // create file /tmp/.dpdk-running to signal that the program is running (for external scripts)
        int fd = open("/tmp/.dpdk-running", O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) {
            printf("Failed to create /tmp/.dpdk-running: %s\n", strerror(errno));
            fflush(stdout);
            return 1;
        }
        close(fd);
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t start = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        // for _ in range(iterations):
        for (int iter = 0; iter < iterations; iter++) {

            const uint16_t nb_rx = rte_eth_rx_burst(port, 0,
                    bufs, BURST_SIZE); // bufs in cvmio pool

            if (unlikely(nb_rx == 0)) {
                /* rx_err++; */
            } else {
                // Copy received packets into mbufs from the shm pool
                size_t nb_copied = 0;
                for (size_t i = 0; i < nb_rx; i++) {
                    enq_objs[nb_copied] = rte_pktmbuf_copy(bufs[i], pool, 0, UINT32_MAX); // TODO not MAX
                    rte_pktmbuf_free(bufs[i]); // return to cvmio_pool
                    if (enq_objs[nb_copied] != NULL)
                        nb_copied++;
                }

                if (nb_copied > 0) {
                    enq_num = rte_ring_sp_enqueue_bulk(&shared->ingress.ring, enq_objs, nb_copied, NULL);
                    if (enq_num == 0)
                        rte_pktmbuf_free_bulk((struct rte_mbuf **)enq_objs, nb_copied); // return to pool
                    else
                        num_enqed += enq_num;
                }

            }

            // receive empty buffers back and return them to pool
            deq_num = rte_ring_sc_dequeue_burst(&shared->egress.ring, deq_objs, BURST_SIZE, NULL);
            if (deq_num > 0) {
                for (size_t j = 0; j < deq_num; j++) {
                    rte_pktmbuf_free(deq_objs[j]); // return to pool TODO: this is propably also wrong
                }
            }

            // Dequeue processed mbufs
            deq_num = rte_ring_sc_dequeue_burst(&shared2->ingress.ring, deq_objs, BURST_SIZE, NULL);
            if (deq_num > 0) {
                size_t nb_copied2 = 0;
                for (size_t i = 0; i < deq_num; i++) {
                    bufs[nb_copied2] = rte_pktmbuf_copy(deq_objs[i], cvmio_pool, 0, UINT32_MAX); // TODO not MAX
                    /* rte_pktmbuf_free(deq_objs[i]); // return to last VNFlet's pool (don't, its not thread safe) */
                    if (bufs[nb_copied2] != NULL) 
                        nb_copied2++;
                    rte_pktmbuf_free(deq_objs[i]); // return to pool1
                }

                if (nb_copied2 > 0) {
                    const uint16_t nb_tx = rte_eth_tx_burst(port, 0,
                            bufs, nb_copied2);

                    /* Free any unsent packets */
                    if (unlikely(nb_tx < nb_copied2)) {
                        uint16_t buf;
                        for (buf = nb_tx; buf < nb_copied2; buf++)
                            rte_pktmbuf_free(bufs[buf]); // return to cvmio_pool
                    }
                }

                // i think this is not necessary. We the buffers are from pool1, so we must free them ourselves:
                // // return empty buffer to previous (our mempool is not atomic, so we have to pass back atomically)
                // size_t nb_returned = rte_ring_sp_enqueue_bulk(&shared2->egress.ring, (void**)(&(deq_objs[0])), deq_num, NULL);
                // if (nb_returned != deq_num) {
                //     printf("Warning: failed to return %lu buffers to shared2->egress\n", deq_num);
                // }

                num_deqed += deq_num;

            }
        }

        shared->keep_running = false; // signal trustlet to stop
        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t end = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        for (int t = 0; t < i; t++) {
            if (handles[t] != NULL) {
                char* _res = threaded_join(handles[t]);
                threaded_free(handles[t]);
            }
        }
        char* _res = threaded_join(iomgr_handle);
        threaded_free(iomgr_handle);

        printf("%d iterations took %.3f s\n", iterations, 1.0 * (end - start) / 1e9);
        printf("Mpps: %.3f\n", num_deqed / ((end - start) / 1e9) / 1e6);
        printf("Successfully enqueued %lu objects\n", num_enqed);
        printf("Successfully dequeued %lu objects\n", num_deqed);
    }

    return 0;
}
