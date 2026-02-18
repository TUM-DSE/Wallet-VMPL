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

#include <rte_eal.h>
#include <rte_errno.h>
#include <rte_ring.h>
#include <rte_mbuf.h>

#include "util.h"
#include "util_run.h"
#include "shm_mempool.h"

// like test6, but with shm between trustlet and guest OS
// needs
// * /etc/default/grub GRUB_CMDLINE_LINUX="isolcpus=1 irqaffinity=0 nohz=on nohz_full=1" update-grub

#define DATA_SIZE 64

static void* DATA_SHARED = NULL;
static __thread bool use_shm_alloc = false;

#define WITH_SHM_ALLOC(expr) ({ \
    use_shm_alloc = true; \
    __typeof__(expr) _result = (expr); \
    use_shm_alloc = false; \
    _result; \
})


// when statically linking DPDK, we make DPDK use these wrappers via --wrap compile flag
extern void *__real_rte_zmalloc(const char *type, size_t size, unsigned align);
void *__wrap_rte_zmalloc(const char *type, size_t size, unsigned align) {
    if (use_shm_alloc) {
        struct shm* shm = (struct shm*)DATA_SHARED;
        if (size == TAILQ_ENTRY_SIZE) {
            return shm->tailq_entry_buf;
        }
        return NULL;
    } else {
        return __real_rte_zmalloc(type, size, align);
    }
    /* return calloc(1, size); */
}

extern const struct rte_memzone *__real_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align);
const struct rte_memzone *__wrap_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align) {
    if (use_shm_alloc) {
        printf("rte_memzone_reserve_aligned: name=%s, len=%lu, socket_id=%d, flags=%u, align=%u\n", name, len, socket_id, flags, align);
        struct rte_memzone *mz = calloc(1, sizeof(struct rte_memzone));
        mz->len = len;
        mz->socket_id = socket_id;
        mz->flags = flags;
        if (len == RING_BUF_SIZE) {
            mz->addr = ((struct shm*)DATA_SHARED)->ingress.buf;
        }
        /* mz->addr = malloc(len); */
        if (!mz->addr) {
            printf("Failed to allocate memory for memzone\n");
        }
        return mz;
    } else {
        return __real_rte_memzone_reserve_aligned(name, len, socket_id, flags, align);
    }
}


int main(int argc, char *argv[]) {
    // with wallet.Wallet() as w:
    monitor_connect();

    // Initialize DPDK EAL with --no-huge for environments without hugepages
    char *eal_args[] = {"test12_run", "--no-huge", "-l", "0"};
    int eal_argc = sizeof(eal_args) / sizeof(eal_args[0]);
    int ret = rte_eal_init(eal_argc, eal_args);
    if (ret < 0) {
        printf("Failed to initialize EAL: %s\n", rte_strerror(rte_errno));
        return -1;
    }

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

    int chain_len = 2;
    int chains[] = {2};
    int chains_len = 1;

    int iterations = 1e8;

    int zygotes[2];
    int trustlets[2];

    // for i in range(chain_len):
    //     zygotes.append(w.create_zygote("../libpal.so", "test4_manifest", "../libsysdb.so"))
    for (int i = 0; i < chain_len; i++) {
        zygotes[i] = create_zygote("../libpal.so", "test12_manifest", "../libsysdb.so");
    }

    // for i in range(chain_len):
    //     trustlets.append(zygotes[i].create_trustlet("./empty.py"))
    for (int i = 0; i < chain_len; i++) {
        trustlets[i] = create_trustlet(zygotes[i], "./empty.py");
    }

    // Allocate shared memory at the same VA the trustlet uses (DATA_SHARED),
    // so pointers within shm (e.g. mbuf buf_addr) are valid in both address spaces.
    void *target_addr = (void *)0x38000000000ULL;
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
    DATA_SHARED = shared;
    shared->legacy_buffer.data[0] = 'I';
    shared->keep_running = true;
    if (!create_shared_memory(trustlets[1], shared, SHARED_SIZE)) {
        printf("Failed to create shared memory\n");
        return -1;
    }
    printf("Shared memory registered\n");

    // Create mbuf pool backed by shared memory
    struct rte_mempool *pool = create_shm_mbuf_pool(shared);
    if (!pool) {
        printf("Failed to create shm mbuf pool\n");
        return -1;
    }
    printf("Mbuf pool created with %u objects\n", pool->populated_size);

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

    int chained = 0;

    // for i in chains:
    for (int idx = 0; idx < chains_len; idx++) {
        int i = chains[idx];

        // #Create chains
        // for c in range(chained,i - 1):
        //     trustlets[c].create_channel(trustlets[c+1])
        for (int c = chained; c < i - 1; c++) {
            // create_channel(trustlets[c], trustlets[c+1]);
        }
        chained += i - chained - 1;

        // #Prepair input data
        struct trustlet_configuration config;
        config.mode[0] = 'a';
        config.shm_addr = shared;

        // #Setup Trustlets
        // for t in range(i - 1):
        //     trustlets[t].invoke_trustlet(b"a", 0)
        printf("185:invoke_trustlet()");
        for (int t = 0; t < i - 1; t++) {
            // Transfer nodes (input->output)
            invoke_trustlet_bin(trustlets[t], &config, sizeof(config), 0);
        }
        // trustlets[i - 1].invoke_trustlet(b"s", 0)
        // End node - use shm mode
        config.mode[0] = 's';
        invoke_trustlet_bin(trustlets[i - 1], &config, sizeof(config), 0);

        // start long-running trustlet
        /* invoke_trustlet(trustlets[1], "s", 0); */
        struct threaded_invoke_handle* handle = threaded_invoke(trustlets[1], 1, "s", 0);
        sleep(1); // give trustlet time to start

        size_t enq_num = 0, num_enqed = 0, deq_num = 0, num_deqed = 0;
        void *enq_objs[BURST_SIZE];
        void *deq_objs[BURST_SIZE];


        printf("Starting %d iterations...\n", iterations);
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t start = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        // for _ in range(iterations):
        for (int iter = 0; iter < iterations; iter++) {
            // Allocate a burst of mbufs from the shm pool
            if (rte_pktmbuf_alloc_bulk(pool, (struct rte_mbuf **)enq_objs, BURST_SIZE) != 0) {
                assert(0 && "rte_pktmbuf_alloc_bulk failed: pool exhausted");
            }
            for (size_t i = 0; i < BURST_SIZE; i++) {
                ((struct rte_mbuf *)enq_objs[i])->data_len = DATA_SIZE;
                ((struct rte_mbuf *)enq_objs[i])->pkt_len = DATA_SIZE;
            }

            enq_num = rte_ring_sp_enqueue_bulk(&shared->ingress.ring, enq_objs, BURST_SIZE, NULL);
            if (enq_num == 0)
                rte_pktmbuf_free_bulk((struct rte_mbuf **)enq_objs, BURST_SIZE);
            else
                num_enqed += enq_num;

            // Dequeue processed mbufs and return to pool
            deq_num = rte_ring_sc_dequeue_burst(&shared->egress.ring, deq_objs, BURST_SIZE, NULL);
            if (deq_num > 0)
                rte_pktmbuf_free_bulk((struct rte_mbuf **)deq_objs, deq_num);
            num_deqed += deq_num;
        }

        shared->keep_running = false; // signal trustlet to stop
        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t end = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        char* _res = threaded_join(handle);
        threaded_free(handle);

        printf("%d iterations took %.3f s\n", iterations, 1.0 * (end - start) / 1e9);
        printf("Mpps: %.3f\n", num_deqed / ((end - start) / 1e9) / 1e6);
        printf("Successfully enqueued %lu objects\n", num_enqed);
        printf("Successfully dequeued %lu objects\n", num_deqed);
    }

    return 0;
}
