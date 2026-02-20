DPDK_EXAMPLES := mirror


DPDK_PATH := $(shell realpath ../../.nix-builds/dpdk)
# DPDK_PATH := /scratch/okelmann/dpdk/build
GLIBC_STATIC := /nix/store/24hs0bbh26w5zfvkv5ps2amfrbwnz8pd-glibc-2.40-66-static/lib
DPDK_LIBS := -Wl,--whole-archive \
	$(DPDK_PATH)/lib/librte_eal.a \
	$(DPDK_PATH)/lib/librte_ring.a \
	$(DPDK_PATH)/lib/librte_log.a \
	$(DPDK_PATH)/lib/librte_kvargs.a \
	$(DPDK_PATH)/lib/librte_telemetry.a \
	$(DPDK_PATH)/lib/librte_mempool.a \
	$(DPDK_PATH)/lib/librte_mempool_ring.a \
	$(DPDK_PATH)/lib/librte_mbuf.a \
	$(DPDK_PATH)/lib/librte_ethdev.a \
	$(DPDK_PATH)/lib/librte_net.a \
	$(DPDK_PATH)/lib/librte_bus_pci.a \
	$(DPDK_PATH)/lib/librte_pci.a \
	$(DPDK_PATH)/lib/librte_bus_vdev.a \
	$(DPDK_PATH)/lib/librte_net_virtio.a \
	-Wl,--no-whole-archive -lm
STATIC_LIBS := -Wl,--whole-archive $(GLIBC_STATIC)/libpthread.a $(GLIBC_STATIC)/libdl.a -Wl,--no-whole-archive
WRAPPERS := -Wl,--wrap=rte_zmalloc -Wl,--wrap=rte_memzone_reserve_aligned

$(DPDK_EXAMPLES): %: %.c ../../module/libwallet/libwallet.a
	gcc -I../libwallet/src/ -include rte_config.h -I$(DPDK_PATH)/include $< -O3 -march=znver3 -g -o $@ -L../libwallet/ -l:libwallet.a -lpthread -lnuma $(DPDK_LIBS)
