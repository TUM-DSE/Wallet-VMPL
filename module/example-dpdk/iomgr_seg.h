#ifndef IOMGR_SEG_H
#define IOMGR_SEG_H

// Shared definitions for splitting the iomgr across several cores.
//
// A single iomgr core shuffles every packet between the driver and all VNFlets
// of the chain (driver->v0, v0->v1, ..., v_{n-1}->driver). For long chains this
// makes the iomgr the bottleneck. To avoid that we spawn one additional iomgr
// core for every VNFLETS_PER_IOMGR VNFlets and split the chain into contiguous
// segments handled by separate iomgr cores arranged as a pipeline:
//
//   driver -> iomgr0 -> [v0..v8] -> iomgr1 -> [v9..v17] -> ... -> driver
//
// Consecutive iomgrs are connected by "handoff" channels. Only the first iomgr
// revokes guest (VMPL3) access on packets entering the chain and only the last
// iomgr restores it before handing packets back to the driver; intermediate
// handoffs keep packets guest-inaccessible.

#include "../example-tests/util.h"

#ifndef CHAINING
#error "CHAINING must be defined before including iomgr_seg.h"
#endif

// One extra iomgr core is spawned for every VNFLETS_PER_IOMGR VNFlets.
#ifndef VNFLETS_PER_IOMGR
#define VNFLETS_PER_IOMGR 9
#endif

// Number of iomgr cores for a chain of CHAINING VNFlets (ceil division).
#define NUM_IOMGR ((CHAINING + VNFLETS_PER_IOMGR - 1) / VNFLETS_PER_IOMGR)

// Channel layout (each CHANNEL_ADDR maps a shared page at a fixed vaddr in every
// address space it is shared into):
//   CHANNEL_ADDR(0)              driver -> iomgr0 input (also holds the mbuf pool)
//   CHANNEL_ADDR(1)              last iomgr -> driver output
//   CHANNEL_ADDR(2 .. 2+C-1)     per-VNFlet ring pairs
//   IOMGR_HANDOFF_ADDR(k)        iomgr k -> iomgr k+1 handoff (k in 0..NUM_IOMGR-2)
#define IOMGR_HANDOFF_ADDR(k) CHANNEL_ADDR(2 + CHAINING + (k))

// First VNFlet index handled by iomgr k.
#define IOMGR_SEG_START(k) ((k) * VNFLETS_PER_IOMGR)
// One past the last VNFlet index handled by iomgr k (clamped to the chain length).
#define IOMGR_SEG_END(k) \
    (((k) + 1) * VNFLETS_PER_IOMGR < CHAINING ? ((k) + 1) * VNFLETS_PER_IOMGR : CHAINING)

// Config passed to an iomgr trustlet: the usual trustlet_configuration plus the
// VNFlet segment [seg_start, seg_end) this iomgr is responsible for.
struct iomgr_config {
    struct trustlet_configuration base;
    int seg_start;
    int seg_end;
};

#endif // IOMGR_SEG_H
