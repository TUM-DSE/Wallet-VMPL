#include <stdio.h>
#include <stdint.h>

// #define VRING_STATS

#ifdef VRING_STATS
/*
 * Minimal layout-compatible struct definitions from DPDK virtio driver
 * internals, for sampling RX virtqueue occupancy from the guest side.
 * These MUST match the DPDK version this application is linked against.
 * Derived from: drivers/net/virtio/{virtqueue.h, virtio_ring.h, virtio_rxtx.h, virtio_cvq.h}
 */
#include <ethdev_driver.h>
#include <rte_spinlock.h>

struct vrs_vring_used_elem { uint32_t id; uint32_t len; };
struct vrs_vring_used {
    uint16_t flags;
    RTE_ATOMIC(uint16_t) idx;
    struct vrs_vring_used_elem ring[];
};
struct vrs_vring {
    unsigned int num;
    rte_iova_t desc_iova;
    void *desc;
    void *avail;
    struct vrs_vring_used *used;
};
struct vrs_vring_packed {
    unsigned int num;
    rte_iova_t desc_iova;
    void *desc;
    void *driver;
    void *device;
};
struct vrs_virtnet_stats {
    uint64_t packets;
    uint64_t bytes;
    uint64_t errors;
    uint64_t multicast;
    uint64_t broadcast;
    uint64_t size_bins[8];
};
struct vrs_virtnet_rx {
    struct rte_mbuf **sw_ring;
    struct rte_mbuf *fake_mbuf;
    uint64_t mbuf_initializer;
    struct rte_mempool *mpool;
    struct vrs_virtnet_stats stats;
};
struct vrs_virtnet_tx {
    const struct rte_memzone *hdr_mz;
    rte_iova_t hdr_mem;
    struct vrs_virtnet_stats stats;
};
struct vrs_virtqueue;
struct vrs_virtnet_ctl {
    const struct rte_memzone *hdr_mz;
    rte_iova_t hdr_mem;
    rte_spinlock_t lock;
    void (*notify_queue)(struct vrs_virtqueue *vq, void *cookie);
    void *notify_cookie;
};
struct virtio_hw;
struct vrs_virtqueue {
    struct virtio_hw *hw;
    union {
        struct {
            struct vrs_vring ring;
        } vq_split;
        struct {
            struct vrs_vring_packed ring;
            bool used_wrap_counter;
            uint16_t cached_flags;
            uint16_t event_flags_shadow;
        } vq_packed;
    };
    uint16_t vq_used_cons_idx;
    uint16_t vq_nentries;
    uint16_t vq_free_cnt;
    uint16_t vq_avail_idx;
    uint16_t vq_free_thresh;
    uint16_t vq_desc_head_idx;
    uint16_t vq_desc_tail_idx;
    uint16_t vq_queue_index;
    void *vq_ring_virt_mem;
    unsigned int vq_ring_size;
    uint16_t mbuf_addr_offset;
    uint64_t mbuf_addr_mask;
    union {
        struct vrs_virtnet_rx rxq;
        struct vrs_virtnet_tx txq;
        struct vrs_virtnet_ctl cq;
    };
};

static inline struct vrs_virtqueue *vrs_rxq_to_vq(void *rxq)
{
    return (struct vrs_virtqueue *)((char *)rxq -
        offsetof(struct vrs_virtqueue, rxq));
}

#ifndef VRING_SAMPLE_INTERVAL_US
#define VRING_SAMPLE_INTERVAL_US 100 /* sample every 100 us */
#endif
#endif /* VRING_STATS */

struct vring_sampling {
    struct vrs_virtqueue *rx_vq;
    uint64_t vrs_samples;
    uint64_t vrs_total_free;
    uint64_t vrs_total_nused;
    unsigned int vrs_aux;
    uint64_t vrs_tsc_hz;
    uint64_t vrs_interval_ticks;
    uint64_t vrs_next_sample;
};

void vring_sampling_init(struct vring_sampling* self, uint16_t port) {
#ifdef VRING_STATS
    self->rx_vq = vrs_rxq_to_vq(
        rte_eth_devices[port].data->rx_queues[0]);
    self->vrs_samples = 0;
    self->vrs_total_free = 0;
    self->vrs_total_nused = 0;
    self->vrs_tsc_hz = rte_get_tsc_hz();
    self->vrs_interval_ticks = self->vrs_tsc_hz / (1000000 / VRING_SAMPLE_INTERVAL_US);
    self->vrs_next_sample = __rdtscp(&self->vrs_aux);
#endif
}

void vring_maybe_sample(struct vring_sampling* self) {
#ifdef VRING_STATS
            {
                uint64_t vrs_now = __rdtscp(&(self->vrs_aux));
                if (vrs_now >= self->vrs_next_sample) {
                    self->vrs_total_free += self->rx_vq->vq_free_cnt;
                    /* used->idx: host-side write index into the used ring (incremented
                     * each time the host deposits a packet into a descriptor).
                     * vq_used_cons_idx: guest-side read index (incremented each time
                     * rx_burst consumes a used descriptor).
                     * The uint16_t cast lets the subtraction wrap correctly.
                     * The difference = packets delivered by host but not yet
                     * consumed by the guest, i.e. the RX backlog. */
                    self->vrs_total_nused += (uint16_t)(self->rx_vq->vq_split.ring.used->idx -
                        self->rx_vq->vq_used_cons_idx);
                    self->vrs_samples++;
                    self->vrs_next_sample = vrs_now + self->vrs_interval_ticks;
                }
            }
#endif
}

void vring_sampling_print(struct vring_sampling* self, uint16_t port) {
#ifdef VRING_STATS
    if (self->vrs_samples > 0) {
        printf("\n=== Vring RX Stats (port %u) ===\n", port);
        printf("Samples: %lu (every %d us)\n", self->vrs_samples, VRING_SAMPLE_INTERVAL_US);
        printf("Ring size: %u descriptors\n", self->rx_vq->vq_nentries);
        printf("Avg free descriptors:       %6.1f / %u (%5.1f%%)\n",
               (double)self->vrs_total_free / self->vrs_samples,
               self->rx_vq->vq_nentries,
               100.0 * self->vrs_total_free / ((double)self->vrs_samples * self->rx_vq->vq_nentries));
        printf("Avg used (pending for RX):  %6.1f / %u (%5.1f%%)\n",
               (double)self->vrs_total_nused / self->vrs_samples,
               self->rx_vq->vq_nentries,
               100.0 * self->vrs_total_nused / ((double)self->vrs_samples * self->rx_vq->vq_nentries));
        printf("Avg inflight (host-side):   %6.1f / %u (%5.1f%%)\n",
               self->rx_vq->vq_nentries -
               (double)self->vrs_total_free / self->vrs_samples -
               (double)self->vrs_total_nused / self->vrs_samples,
               self->rx_vq->vq_nentries,
               100.0 * (self->rx_vq->vq_nentries -
               (double)self->vrs_total_free / self->vrs_samples -
               (double)self->vrs_total_nused / self->vrs_samples) / self->rx_vq->vq_nentries);
    }
#endif
}
