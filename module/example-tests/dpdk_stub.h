// To be used to make trustlets etc compile even when they dont use dpdk

#include <rte_eal.h>
#include <rte_errno.h>
#include <rte_ring.h>
#include <rte_memzone.h>

void *__wrap_rte_zmalloc(const char *type, size_t size, unsigned align) {
    return NULL;
}

const struct rte_memzone *__wrap_rte_memzone_reserve_aligned(const char *name, size_t len, int socket_id, unsigned flags, unsigned align) {
    return NULL;
}
