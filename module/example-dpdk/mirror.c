#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <sys/types.h>
#include <sys/queue.h>
#include <setjmp.h>
#include <stdarg.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <getopt.h>
#include <signal.h>
#include <stdbool.h>
#include <x86intrin.h> // gcc instrinsics

#include <rte_common.h>
#include <rte_log.h>
#include <rte_malloc.h>
#include <rte_memory.h>
#include <rte_memcpy.h>
#include <rte_eal.h>
#include <rte_launch.h>
#include <rte_cycles.h>
#include <rte_prefetch.h>
#include <rte_lcore.h>
#include <rte_per_lcore.h>
#include <rte_branch_prediction.h>
#include <rte_interrupts.h>
#include <rte_random.h>
#include <rte_debug.h>
#include <rte_ether.h>
#include <rte_ethdev.h>
#include <rte_mempool.h>
#include <rte_mbuf.h>

#include "vring_trace.h"

#define RX_RING_SIZE 1024
#define TX_RING_SIZE 1024
#define NUM_MBUFS 2*512
#define MBUF_CACHE_SIZE 250

#ifndef BURST_SIZE
#define BURST_SIZE 32
#endif

#ifndef LLC_SIZE
#define LLC_SIZE 512*1024 // 512 kB (for weak laptops)
/* #define LLC_SIZE 512*1024*1024 // 512 MB (-> requires ~25GB mempool including head/tailroom)*/
#endif

#ifndef PACKET_SIZE
#define PACKET_SIZE 64
#endif
/* #define PACKET_POOL_SIZE 2ull*LLC_SIZE / PACKET_SIZE */
#define PACKET_POOL_SIZE 2ull*LLC_SIZE / RTE_MBUF_DEFAULT_BUF_SIZE - 1

#ifndef PER_VNFLET_WORKLOAD_NS
#define PER_VNFLET_WORKLOAD_NS 0
#endif

#define QUIET

/* Configuration */
static const struct rte_eth_conf port_conf_default = {
    .rxmode = {
        .max_lro_pkt_size = RTE_ETHER_MAX_LEN,
    },
};

static volatile bool force_quit;

/* Signal handler */
static void
signal_handler(int signum)
{
    if (signum == SIGINT || signum == SIGTERM) {
        printf("\n\nSignal %d received, preparing to exit...\n", signum);
        force_quit = true;
    }
}

static void __attribute__((noinline)) ndelay_accurate(int cycles) {
/* static inline void ndelay_accurate(int cycles) { */
    unsigned int _aux;
    uint64_t start = __rdtscp(&_aux);
    uint64_t duration = 0;
    while (duration < cycles) {
        asm volatile("nop"::);
        duration = __rdtscp(&_aux) - start;
    }
}

/* Port initialization function */
static inline int
port_init(uint16_t port, struct rte_mempool *mbuf_pool)
{
    struct rte_eth_conf port_conf = port_conf_default;
    const uint16_t rx_rings = 1, tx_rings = 1;
    uint16_t nb_rxd = RX_RING_SIZE;
    uint16_t nb_txd = TX_RING_SIZE;
    int retval;
    uint16_t q;
    struct rte_eth_dev_info dev_info;
    struct rte_eth_txconf txconf;

    if (!rte_eth_dev_is_valid_port(port))
        return -1;

    retval = rte_eth_dev_info_get(port, &dev_info);
    if (retval != 0) {
        printf("Error during getting device (port %u) info: %s\n",
                port, strerror(-retval));
        return retval;
    }

    if (dev_info.tx_offload_capa & RTE_ETH_TX_OFFLOAD_MBUF_FAST_FREE)
        port_conf.txmode.offloads |= RTE_ETH_TX_OFFLOAD_MBUF_FAST_FREE;

    /* Configure the Ethernet device. */
    retval = rte_eth_dev_configure(port, rx_rings, tx_rings, &port_conf);
    if (retval != 0)
        return retval;

    retval = rte_eth_dev_adjust_nb_rx_tx_desc(port, &nb_rxd, &nb_txd);
    if (retval != 0)
        return retval;

    /* Allocate and set up 1 RX queue per Ethernet port. */
    for (q = 0; q < rx_rings; q++) {
        retval = rte_eth_rx_queue_setup(port, q, nb_rxd,
                rte_eth_dev_socket_id(port), NULL, mbuf_pool);
        if (retval < 0)
            return retval;
    }

    txconf = dev_info.default_txconf;
    txconf.offloads = port_conf.txmode.offloads;
    /* Allocate and set up 1 TX queue per Ethernet port. */
    for (q = 0; q < tx_rings; q++) {
        retval = rte_eth_tx_queue_setup(port, q, nb_txd,
                rte_eth_dev_socket_id(port), &txconf);
        if (retval < 0)
            return retval;
    }

    /* Start the Ethernet port. */
    retval = rte_eth_dev_start(port);
    if (retval < 0)
        return retval;

    /* Display the port MAC address. */
    struct rte_ether_addr addr;
    retval = rte_eth_macaddr_get(port, &addr);
    if (retval != 0)
        return retval;

    printf("Port %u MAC: %02x:%02x:%02x:%02x:%02x:%02x\n",
            port, RTE_ETHER_ADDR_BYTES(&addr));

    /* Enable RX in promiscuous mode for the Ethernet device. */
    retval = rte_eth_promiscuous_enable(port);
    if (retval != 0)
        return retval;

    return 0;
}

/* Hexdump function */
static void
hexdump(const void *data, size_t size)
{
    const unsigned char *p = data;
    size_t i, j;

    for (i = 0; i < size; i += 16) {
        printf("%08zx: ", i);

        /* Print hex values */
        for (j = 0; j < 16; j++) {
            if (i + j < size)
                printf("%02x ", p[i + j]);
            else
                printf("   ");
        }

        printf(" |");

        /* Print ASCII values */
        for (j = 0; j < 16 && i + j < size; j++) {
            unsigned char c = p[i + j];
            printf("%c", isprint(c) ? c : '.');
        }

        printf("|\n");
    }
}

/* Main packet processing loop */
static void
lcore_spam(struct rte_mempool *mbuf_pool)
{
    uint16_t port;
    uint64_t packet_count = 0;
    uint64_t tx_count = 0;

    void *objs[BURST_SIZE];
    size_t i, j;

    // Initialize dummy objects
    for (i = 0; i < BURST_SIZE; i++) {
        objs[i] = (void *)(uintptr_t)(i + 1);
    }

    // Initialize packet buffers
    struct rte_mbuf** mbufs = calloc(PACKET_POOL_SIZE, sizeof(struct rte_mbuf*));
    /* void* buf; */
    /* for (i = 0; i < PACKET_POOL_SIZE; i++) { */
    /*     mbufs[i] = rte_pktmbuf_alloc(mbuf_pool); */
    /*     if (mbufs[i] == NULL) { */
    /*         printf("Failed to allocate packet %ld\n", i); */
    /*         return; */
    /*     } */
    /*     buf = rte_pktmbuf_append(mbufs[i], PACKET_SIZE); */
    /*     if (buf == NULL) { */
    /*         printf("Failed to append %d bytes to packet %ld\n", PACKET_SIZE, i); */
    /*         return; */
    /*     } */
    /*     memset(buf, -1, PACKET_SIZE); */
    /* } */

    /*
     * Check that the port is on the same NUMA node as the polling thread
     * for best performance.
     */
    RTE_ETH_FOREACH_DEV(port)
        if (rte_eth_dev_socket_id(port) >= 0 &&
                rte_eth_dev_socket_id(port) !=
                        (int)rte_socket_id())
            printf("WARNING, port %u is on remote NUMA node to "
                    "polling thread.\n\tPerformance will "
                    "not be optimal.\n", port);

    printf("\nCore %u receiving packets. [Ctrl+C to quit]\n",
            rte_lcore_id());

    /* Run until the application is quit or killed. */
    for (;;) {
        /* Check if we should exit */
        if (force_quit)
            break;


        for (j = 0; j < 100000; j++) {
#ifdef MEASURE_MINMAX
            uint64_t enq_start = get_cycles();
#endif

            for (i=0; i<BURST_SIZE; i++) {
                mbufs[i] = rte_pktmbuf_alloc(mbuf_pool);
                // TODO check
                rte_pktmbuf_append(mbufs[i], PACKET_SIZE);
                // TODO check
            }

            /* size_t mbuf_idx = (i*BURST_SIZE)%PACKET_POOL_SIZE; */
            size_t mbuf_idx = 0;
            /* ret = rte_ring_sp_enqueue_bulk(0, (void**)(&(mbufs[mbuf_idx])), BURST_SIZE, NULL); */
            const uint16_t ret = rte_eth_tx_burst(0, 0,
                    &(mbufs[mbuf_idx]), BURST_SIZE);

#ifdef MEASURE_MINMAX
            uint64_t enq_end = get_cycles();
            op_cycles = enq_end - enq_start;
#endif

            if (ret == BURST_SIZE) {
                /* prod_stats.total_enqueued += BURST_SIZE; */
#ifdef MEASURE_MINMAX
                prod_stats.total_cycles += op_cycles;

                if (op_cycles < prod_stats.min_cycles) {
                    prod_stats.min_cycles = op_cycles;
                }
                if (op_cycles > prod_stats.max_cycles) {
                    prod_stats.max_cycles = op_cycles;
                }
#endif
            } else {
                /* prod_stats.enqueue_failures++; */
                // Backoff slightly on failure
                /* rte_pause(); */
            }
            i += BURST_SIZE;
        }
    }
}

/* Main packet processing loop */
static void
lcore_mirror(void)
{
    uint16_t port = rte_eth_find_next(0);
    uint64_t packet_count = 0;
    uint64_t tx_count = 0;
    volatile uint64_t rx_err = 0;
    volatile uint64_t tx_err = 0;

    /*
     * Check that the port is on the same NUMA node as the polling thread
     * for best performance.
     */
    RTE_ETH_FOREACH_DEV(port)
        if (rte_eth_dev_socket_id(port) >= 0 &&
                rte_eth_dev_socket_id(port) !=
                        (int)rte_socket_id())
            printf("WARNING, port %u is on remote NUMA node to "
                    "polling thread.\n\tPerformance will "
                    "not be optimal.\n", port);

    uint64_t sleep = (uint64_t)((double)PER_VNFLET_WORKLOAD_NS * rte_get_tsc_hz() / 1e9);

    printf("\nCore %u receiving packets. [Ctrl+C to quit]\n",
            rte_lcore_id());
    // create file /tmp/.dpdk-running to signal that the program is running (for external scripts)
    int fd = open("/tmp/.dpdk-running", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) {
        printf("Failed to create /tmp/.dpdk-running: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }
    close(fd);

    RTE_ETH_FOREACH_DEV(port) {
    /* Run until the application is quit or killed. */
    struct rte_mbuf *bufs[BURST_SIZE];
    struct vring_sampling sampler;
    vring_sampling_init(&sampler, port);
    for (;;) {
        /* Check if we should exit */
        if (force_quit)
            break;

        /* Receive packets on all ports */
        /* RTE_ETH_FOREACH_DEV(port) { */
            const uint16_t nb_rx = rte_eth_rx_burst(port, 0,
                    bufs, BURST_SIZE);

            vring_maybe_sample(&sampler);
            if (unlikely(nb_rx == 0)) {
                rx_err++;
                continue;
            }

#ifndef QUIET
            /* Process received packets */
            for (int i = 0; i < nb_rx; i++) {
                struct rte_mbuf *pkt = bufs[i];
                void *pkt_data = rte_pktmbuf_mtod(pkt, void*);

                printf("\n=== Packet #%lu at %p (Port %u) ===\n",
                       ++packet_count, pkt_data, port);
                printf("Length: %u bytes\n", pkt->pkt_len);
                printf("Data length: %u bytes\n", pkt->data_len);

                /* Dump packet contents */
                hexdump(pkt_data, pkt->data_len);
            }
#endif
            ndelay_accurate(sleep * nb_rx); // simulate per-packet processing time

            /* Send packets back out on the same port */
            const uint16_t nb_tx = rte_eth_tx_burst(port, 0,
                    bufs, nb_rx);

            if (nb_tx > 0) {
                tx_count += nb_tx;
#ifndef QUIET
                printf("=== TX: Sent %u packets back on port %u (Total sent: %lu) ===\n",
                       nb_tx, port, tx_count);
#endif
            }

            /* Free any unsent packets */
            if (unlikely(nb_tx < nb_rx)) {
                uint16_t buf;
                tx_err += nb_rx - nb_tx;
#ifndef QUIET
                printf("Warning: Only sent %u out of %u packets\n", nb_tx, nb_rx);
#endif
                for (buf = nb_tx; buf < nb_rx; buf++)
                    rte_pktmbuf_free(bufs[buf]);
            }
        /* } */
    }
    vring_sampling_print(&sampler, port);
    printf("\nCore %u exiting. Total RX: %lu, Total TX: %lu, RX Errors: %lu, TX Errors: %lu\n",
            rte_lcore_id(), packet_count, tx_count, rx_err, tx_err);
}
}

/*
 * The main function, which does initialization and calls the per-lcore
 * functions.
 */
int
main(int argc, char *argv[])
{
    unsigned nb_ports;
    uint16_t portid;
    struct rte_mempool *mbuf_pool;

    /* Initialize the Environment Abstraction Layer (EAL). */
    int ret = rte_eal_init(argc, argv);
    if (ret < 0)
        rte_exit(EXIT_FAILURE, "Error with EAL initialization\n");

    argc -= ret;
    argv += ret;

    /* Install signal handlers */
    force_quit = false;
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    nb_ports = rte_eth_dev_count_avail();
    if (nb_ports == 0)
        rte_exit(EXIT_FAILURE, "No Ethernet ports - bye\n");

    printf("Found %u Ethernet ports\n", nb_ports);

    /* Creates a new mempool in memory to hold the mbufs. */
    mbuf_pool = rte_pktmbuf_pool_create("MBUF_POOL", NUM_MBUFS * nb_ports,
        MBUF_CACHE_SIZE, 0, RTE_MBUF_DEFAULT_BUF_SIZE, rte_socket_id());
    printf("1\n");

    if (mbuf_pool == NULL)
        rte_exit(EXIT_FAILURE, "Cannot create mbuf pool\n");

    /* Initialize all ports. */
    RTE_ETH_FOREACH_DEV(portid)
        if (port_init(portid, mbuf_pool) != 0)
            rte_exit(EXIT_FAILURE, "Cannot init port %"PRIu16 "\n",
                    portid);

    if (rte_lcore_count() > 1)
        printf("\nWARNING: Too many lcores enabled. Only 1 used.\n");

    printf("2\n");
    /* Call lcore_main on the main lcore only. */
    /* lcore_spam(mbuf_pool); */
    lcore_mirror();

    /* Clean up */
    printf("\nShutting down...\n");
    RTE_ETH_FOREACH_DEV(portid) {
        printf("Closing port %d...", portid);
        ret = rte_eth_dev_stop(portid);
        if (ret != 0)
            printf("rte_eth_dev_stop: err=%d, port=%d\n", ret, portid);
        rte_eth_dev_close(portid);
        printf(" Done\n");
    }

    /* Clean up the EAL */
    rte_eal_cleanup();
    printf("Bye...\n");

    return 0;
}

