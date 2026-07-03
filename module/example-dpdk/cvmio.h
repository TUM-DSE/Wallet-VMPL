
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

#define RX_RING_SIZE 1024
#define TX_RING_SIZE 1024
// cvmio_pool must supply mbufs for the NIC RX ring (up to RX_RING_SIZE), the
// per-packet TX copies (rte_pktmbuf_copy in the iomgr driver), and the TX ring
// (up to TX_RING_SIZE) all at once. 2*512 = 1024 is barely one ring's worth, so
// under sustained bulk TX the pool drains, rte_pktmbuf_copy() returns NULL and
// packets are silently dropped -> the iperf VNFlet transfer collapses after its
// initial burst. Size it well above RX_RING+TX_RING+in-flight, but not so large
// it exceeds DPDK's --no-huge default memory (the driver runs --no-huge, and a
// ~40MB pool from 16*1024 mbufs fails EAL pool creation). 4*1024 (~10MB) clears
// RX_RING(1024)+TX_RING(1024)+cache+burst with headroom.
#define NUM_MBUFS (4*1024)
#define MBUF_CACHE_SIZE 250

#ifndef BURST_SIZE
#define BURST_SIZE 1
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

#define QUIET

/* Configuration */
static const struct rte_eth_conf port_conf_default = {
    .rxmode = {
        .max_lro_pkt_size = RTE_ETHER_MAX_LEN,
    },
};

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

    /* TX offloads for the iperf VNFlet path: the trustlet's F-Stack emits
     * TSO super-frames with RTE_MBUF_F_TX_TCP_SEG/TCP_CKSUM + tso_segsz set
     * (metadata survives the rte_pktmbuf_copy into cvmio_pool), so this port
     * must accept csum/TSO mbufs and multi-segment chains. Gated on the
     * advertised capability, same as F-Stack's own init gates on the proven
     * vhost_user client rig (virtio-pci advertises all four here; a missing
     * one indicates a virtio feature-negotiation problem, hence the loud
     * warning -- it would otherwise surface only as a perf regression). */
    {
        static const struct { uint64_t bit; const char *name; } tx_offloads[] = {
            { RTE_ETH_TX_OFFLOAD_TCP_CKSUM,  "TCP_CKSUM"  },
            { RTE_ETH_TX_OFFLOAD_UDP_CKSUM,  "UDP_CKSUM"  },
            { RTE_ETH_TX_OFFLOAD_TCP_TSO,    "TCP_TSO"    },
            { RTE_ETH_TX_OFFLOAD_MULTI_SEGS, "MULTI_SEGS" },
        };
        for (size_t i = 0; i < sizeof(tx_offloads) / sizeof(tx_offloads[0]); i++) {
            if (dev_info.tx_offload_capa & tx_offloads[i].bit)
                port_conf.txmode.offloads |= tx_offloads[i].bit;
            else
                printf("WARNING: port %u does not advertise TX offload %s\n",
                       port, tx_offloads[i].name);
        }
        printf("port %u txmode.offloads = 0x%" PRIx64 "\n",
               port, (uint64_t)port_conf.txmode.offloads);
    }

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


struct rte_mempool *cvmio_init() {
    unsigned nb_ports;
    uint16_t portid;
    struct rte_mempool *mbuf_pool;

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

    return mbuf_pool;
}


void cvmio_deinit() {
    uint16_t portid;
    int ret;
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
}
