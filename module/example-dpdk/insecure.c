#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <inttypes.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

#include <rte_eal.h>
#include <rte_cycles.h>
#include <rte_memory.h>
#include <rte_lcore.h>
#include <rte_launch.h>
#include <rte_mbuf.h>
#include <rte_errno.h>
#include <rte_ethdev.h>
#include <rte_ring.h>

// Multi-threaded insecure baseline: driver + VNFlet threads, no isolation,
// no mbuf copies between stages. Packets flow through SPSC rings as pointers.
//
//  NIC -rx-> Driver -[ring0]-> VNFlet0 -[ring1]-> ... -[ringN]-> Driver -tx-> NIC

#ifndef PER_VNFLET_WORKLOAD_NS
#define PER_VNFLET_WORKLOAD_NS 0
#endif

#ifndef CHAINING
#define CHAINING 2
#endif

#ifndef RUNTIME_S
#define RUNTIME_S 30
#endif

#ifndef BURST_SIZE
#define BURST_SIZE 1
#endif

#define RING_SIZE 1024

#define RX_RING_SIZE 1024
#define TX_RING_SIZE 1024
#define NUM_MBUFS (CHAINING+2)*512 // should be 512
/* #define NUM_MBUFS 2*512 */
#define MBUF_CACHE_SIZE 250

#include "workload.h"
#include "ipsec.h"
#include "ids.h"

// #define REAL_WORKLOAD

/* #define SIMPLE_POOL */
#ifdef SIMPLE_POOL
#define SPOOL_MAX 2048
#include "pktmbuf_pool.h"
#endif /* SIMPLE_POOL */

// --- timing ---

static inline uint64_t get_cycles(void) { return rte_rdtsc(); }

static inline void ndelay(uint64_t cycles) {
    uint64_t start = get_cycles();
    while (get_cycles() - start < cycles)
        asm volatile("nop"::);
}

// --- port init (same as noiomgr_test.c / cvmio.h) ---

static const struct rte_eth_conf port_conf_default = {
    .rxmode = { .max_lro_pkt_size = RTE_ETHER_MAX_LEN },
};

static inline int
port_init(uint16_t port, struct rte_mempool *mbuf_pool)
{
    struct rte_eth_conf port_conf = port_conf_default;
    uint16_t nb_rxd = RX_RING_SIZE, nb_txd = TX_RING_SIZE;
    int retval;
    struct rte_eth_dev_info dev_info;
    struct rte_eth_txconf txconf;

    if (!rte_eth_dev_is_valid_port(port))
        return -1;

    retval = rte_eth_dev_info_get(port, &dev_info);
    if (retval != 0) return retval;

    if (dev_info.tx_offload_capa & RTE_ETH_TX_OFFLOAD_MBUF_FAST_FREE)
        port_conf.txmode.offloads |= RTE_ETH_TX_OFFLOAD_MBUF_FAST_FREE;

    retval = rte_eth_dev_configure(port, 1, 1, &port_conf);
    if (retval != 0) return retval;

    retval = rte_eth_dev_adjust_nb_rx_tx_desc(port, &nb_rxd, &nb_txd);
    if (retval != 0) return retval;

    retval = rte_eth_rx_queue_setup(port, 0, nb_rxd,
            rte_eth_dev_socket_id(port), NULL, mbuf_pool);
    if (retval < 0) return retval;

    txconf = dev_info.default_txconf;
    txconf.offloads = port_conf.txmode.offloads;
    retval = rte_eth_tx_queue_setup(port, 0, nb_txd,
            rte_eth_dev_socket_id(port), &txconf);
    if (retval < 0) return retval;

    retval = rte_eth_dev_start(port);
    if (retval < 0) return retval;

    struct rte_ether_addr addr;
    rte_eth_macaddr_get(port, &addr);
    printf("Port %u MAC: %02x:%02x:%02x:%02x:%02x:%02x\n",
            port, RTE_ETHER_ADDR_BYTES(&addr));

    rte_eth_promiscuous_enable(port);
    return 0;
}

// --- shared state ---

// CHAINING + 1 rings: ring[i] connects stage i-1 output to stage i input.
// ring[0]: driver -> VNFlet 0
// ring[CHAINING]: VNFlet CHAINING-1 -> driver
static struct rte_ring *rings[CHAINING + 1];

static volatile int driver_done = 0;

// --- VNFlet thread ---

struct vnflet_args {
    int id;
};

static int
vnflet_thread(void *arg)
{
    struct vnflet_args *va = (struct vnflet_args *)arg;
    int id = va->id;
    struct rte_ring *in  = rings[id];
    struct rte_ring *out = rings[id + 1];
    void *objs[BURST_SIZE];
    uint64_t total = 0;

    struct workload *wl = workload_alloc();
    uint64_t workload_cycles = (uint64_t)((double)(PER_VNFLET_WORKLOAD_NS) / 1e9 * rte_get_tsc_hz());

    /* test keys - replace with real keys for production */
    static const uint8_t test_enc_key[16] = {
        0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef,
        0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54, 0x32, 0x10
    };
    static const uint8_t test_auth_key[16] = {
        0x10, 0x32, 0x54, 0x76, 0x98, 0xba, 0xdc, 0xfe,
        0xef, 0xcd, 0xab, 0x89, 0x67, 0x45, 0x23, 0x01
    };

    struct ipsec_sa sa;
    ipsec_sa_init(&sa, test_enc_key, test_auth_key, 1, 32);
    uint32_t spi = 0x1000;

    int is_first = (id == 0);
    int is_last  = (id == CHAINING - 1);

    ids_init();

    printf("VNFlet %d starting on lcore %u\n", id, rte_lcore_id());

    while (!__atomic_load_n(&driver_done, __ATOMIC_ACQUIRE)) {
        unsigned n = rte_ring_sc_dequeue_burst(in, objs, BURST_SIZE, NULL);
        if (n == 0)
            continue;

        artificial_workload(wl, n);
        if (workload_cycles > 0)
            ndelay(workload_cycles * n);

#ifdef REAL_WORKLOAD
        if (is_first) {
            for (unsigned i = 0; i < n; i++) {
                ipsec_esp_encap(objs[i], &sa, spi, 0);
                ipsec_chacha_encrypt_auth(objs[i], &sa);
                ipsec_ip_encap(objs[i], 50, 0x1, 0x2);
            }
        } else if (is_last) {
            for (unsigned i = 0; i < n; i++) {
                ipsec_ip_decap(objs[i]);
                ipsec_chacha_decrypt_auth(objs[i], &sa);
                ipsec_esp_decap(objs[i], &sa);
            }
        } else {
            for (unsigned i = 0; i < n; i++) {
                struct rte_mbuf *pkt = objs[i];
                ids_scan(rte_pktmbuf_mtod(pkt, const char *),
                         rte_pktmbuf_data_len(pkt));
            }
        }
#endif

        unsigned sent = rte_ring_sp_enqueue_bulk(out, objs, n, NULL);
        if (sent == 0) {
            // Drop: free mbufs so they return to the pool
            /* rte_pktmbuf_free_bulk((struct rte_mbuf **)objs, n); */
        } else {
            total += sent;
        }
    }

    // Drain remaining
    unsigned n;
    do {
        n = rte_ring_sc_dequeue_burst(in, objs, BURST_SIZE, NULL);
        if (n > 0) {
            unsigned sent = rte_ring_sp_enqueue_bulk(out, objs, n, NULL);
            if (sent == 0) {
                /* rte_pktmbuf_free_bulk((struct rte_mbuf **)objs, n); */
            } else
                total += sent;
        }
    } while (n > 0);

    ipsec_sa_free(&sa);
    printf("VNFlet %d done: %" PRIu64 " packets forwarded\n", id, total);
    return 0;
}

// --- main / driver ---

int main(int argc, char **argv)
{
    int ret;
    uint16_t portid;
    struct rte_mempool *mbuf_pool;

    ret = rte_eal_init(argc, argv);
    if (ret < 0)
        rte_exit(EXIT_FAILURE, "EAL init failed\n");

    if (rte_lcore_count() < (unsigned)(CHAINING + 1))
        rte_exit(EXIT_FAILURE, "Need at least %d lcores (1 driver + %d VNFlets), have %u\n",
                 CHAINING + 1, CHAINING, rte_lcore_count());

    unsigned nb_ports = rte_eth_dev_count_avail();
    if (nb_ports == 0)
        rte_exit(EXIT_FAILURE, "No Ethernet ports\n");

#ifdef SIMPLE_POOL
    {
        unsigned n = NUM_MBUFS * nb_ports;
        unsigned elt = sizeof(struct rte_mbuf) + RTE_MBUF_DEFAULT_BUF_SIZE;
        mbuf_pool = rte_mempool_create_empty("MBUF_POOL", n, elt,
            0 /* cache_size */, sizeof(struct rte_pktmbuf_pool_private),
            rte_socket_id(), 0);
        if (!mbuf_pool)
            rte_exit(EXIT_FAILURE, "Cannot create mempool: %s\n", rte_strerror(rte_errno));
        if (rte_mempool_set_ops_byname(mbuf_pool, "spool", &g_spool) != 0)
            rte_exit(EXIT_FAILURE, "Cannot set spool ops\n");
        rte_pktmbuf_pool_init(mbuf_pool, NULL);
        if (rte_mempool_populate_default(mbuf_pool) < 0)
            rte_exit(EXIT_FAILURE, "Cannot populate mempool: %s\n", rte_strerror(rte_errno));
        rte_mempool_obj_iter(mbuf_pool, rte_pktmbuf_init, NULL);
        printf("SIMPLE_POOL: non-atomic stack, no per-lcore cache, %u mbufs\n",
               mbuf_pool->populated_size);
    }
#else
    mbuf_pool = rte_pktmbuf_pool_create("MBUF_POOL", NUM_MBUFS * nb_ports,
        MBUF_CACHE_SIZE, 0, RTE_MBUF_DEFAULT_BUF_SIZE, rte_socket_id());
    if (mbuf_pool == NULL)
        rte_exit(EXIT_FAILURE, "Cannot create mbuf pool\n");
#endif

    RTE_ETH_FOREACH_DEV(portid)
        if (port_init(portid, mbuf_pool) != 0)
            rte_exit(EXIT_FAILURE, "Cannot init port %"PRIu16 "\n", portid);

    uint16_t port = rte_eth_find_next(0);

    // Create CHAINING + 1 SPSC rings
    for (int i = 0; i < CHAINING + 1; i++) {
        char name[32];
        snprintf(name, sizeof(name), "ring_%d", i);
        rings[i] = rte_ring_create(name, RING_SIZE, rte_socket_id(),
                                   RING_F_SP_ENQ | RING_F_SC_DEQ);
        if (rings[i] == NULL)
            rte_exit(EXIT_FAILURE, "Cannot create ring %d\n", i);
    }

    printf("insecure baseline: driver + %d VNFlet threads, no copies\n", CHAINING);
    printf("CHAINING=%d, PER_VNFLET_WORKLOAD_NS=%d, BURST_SIZE=%d, RUNTIME_S=%d\n",
           CHAINING, PER_VNFLET_WORKLOAD_NS, BURST_SIZE, RUNTIME_S);

    // Launch VNFlet threads on worker lcores
    static struct vnflet_args vargs[CHAINING];
    unsigned lcore_id;
    int vnflet_idx = 0;
    RTE_LCORE_FOREACH_WORKER(lcore_id) {
        if (vnflet_idx >= CHAINING)
            break;
        vargs[vnflet_idx].id = vnflet_idx;
        printf("Launching VNFlet %d on lcore %u\n", vnflet_idx, lcore_id);
        rte_eal_remote_launch(vnflet_thread, &vargs[vnflet_idx], lcore_id);
        vnflet_idx++;
    }

    // Signal running
    int fd = open("/tmp/.dpdk-running", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) close(fd);

    // Driver loop on main lcore
    struct rte_ring *to_chain   = rings[0];
    struct rte_ring *from_chain = rings[CHAINING];
    struct rte_mbuf *bufs[BURST_SIZE];
    void *objs[BURST_SIZE];
    uint64_t total_rx = 0, total_tx = 0;

    uint64_t start_cycles = get_cycles();
    uint64_t deadline = start_cycles + (uint64_t)((double)RUNTIME_S * rte_get_tsc_hz());

    while (get_cycles() < deadline) {
        // RX from NIC -> enqueue to first VNFlet
        uint16_t nb_rx = rte_eth_rx_burst(port, 0, bufs, BURST_SIZE);
        if (nb_rx > 0) {
            unsigned enq = rte_ring_sp_enqueue_bulk(to_chain, (void **)bufs, nb_rx, NULL);
            if (enq == 0)
                rte_pktmbuf_free_bulk(bufs, nb_rx);
            else
                total_rx += enq;
        }

        // Dequeue from last VNFlet -> TX to NIC
        unsigned nb_out = rte_ring_sc_dequeue_burst(from_chain, objs, BURST_SIZE, NULL);
        if (nb_out > 0) {
            uint16_t nb_tx = rte_eth_tx_burst(port, 0, (struct rte_mbuf **)objs, nb_out);
            if (unlikely(nb_tx < nb_out)) {
                for (uint16_t i = nb_tx; i < nb_out; i++)
                    rte_pktmbuf_free((struct rte_mbuf *)objs[i]);
            }
            total_tx += nb_tx;
        }
    }

    uint64_t end_cycles = get_cycles();
    __atomic_store_n(&driver_done, 1, __ATOMIC_RELEASE);

    // Wait for VNFlets
    RTE_LCORE_FOREACH_WORKER(lcore_id) {
        rte_eal_wait_lcore(lcore_id);
    }

    // Drain anything left in the last ring after VNFlets flushed
    unsigned nb_out;
    do {
        nb_out = rte_ring_sc_dequeue_burst(from_chain, objs, BURST_SIZE, NULL);
        if (nb_out > 0) {
            uint16_t nb_tx = rte_eth_tx_burst(port, 0, (struct rte_mbuf **)objs, nb_out);
            if (nb_tx < nb_out)
                for (uint16_t i = nb_tx; i < nb_out; i++)
                    rte_pktmbuf_free((struct rte_mbuf *)objs[i]);
            total_tx += nb_tx;
        }
    } while (nb_out > 0);

    double elapsed_s = (double)(end_cycles - start_cycles) / rte_get_tsc_hz();

    printf("\n=== Results ===\n");
    printf("Elapsed: %.3f s\n", elapsed_s);
    printf("Total RX: %" PRIu64 "\n", total_rx);
    printf("Total TX: %" PRIu64 "\n", total_tx);
    printf("RX Mpps: %.3f\n", total_rx / elapsed_s / 1e6);
    printf("TX Mpps: %.3f\n", total_tx / elapsed_s / 1e6);

    unlink("/tmp/.dpdk-running");

    RTE_ETH_FOREACH_DEV(portid) {
        rte_eth_dev_stop(portid);
        rte_eth_dev_close(portid);
    }
    for (int i = 0; i < CHAINING + 1; i++)
        rte_ring_free(rings[i]);
    rte_eal_cleanup();

    return 0;
}
