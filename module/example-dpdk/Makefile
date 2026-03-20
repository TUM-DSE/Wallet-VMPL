DPDK_EXAMPLES := mirror insecure
TRUSTLETS := noiomgr_trustlet iomgr_trustlet
RUNNERS := noiomgr_run iomgr_run
CFLAGS :=

all: $(DPDK_EXAMPLES) $(TRUSTLETS) $(RUNNERS) simple_slick_fs
	@make -C ../../ gramine

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
WRAPPERS := -Wl,--wrap=rte_zmalloc -Wl,--wrap=rte_memzone_reserve_aligned -Wl,--wrap=rte_memzone_reserve

NUMA_LIB := /nix/store/557rbsz8mbv0w97gw8v2ni7x9d40x509-numactl-2.0.18/lib
ATOMIC_LIB := /nix/store/f1ii69v7p27z1r5zybmlbld3bdzm6a5f-gcc-13.2.0-lib/lib
GLIBC_LIB := /nix/store/35pq4hr29c3sl79lgfwgsvd9nwzyp4am-glibc-2.39-5/lib
BSD_INCLUDE := /nix/store/xiw9h3ssfsj1qnap4nzg2hzhq8zc54r5-libbsd-0.11.8-dev/include
DPDK_SRC := /scratch/okelmann/dpdk-cvms

$(DPDK_EXAMPLES): %: %.c ../../module/libwallet/libwallet.a
	gcc -I../libwallet/src/ -include rte_config.h -I$(DPDK_PATH)/include -I$(DPDK_SRC)/lib/ethdev -I$(DPDK_SRC)/lib/eal/include -I$(BSD_INCLUDE) $< -O3 -march=znver3 -mssse3 -g -o $@ -L../libwallet/ -l:libwallet.a -lpthread -lnuma $(DPDK_LIBS) $(CFLAGS)

noiomgr_trustlet: %: %.c
	gcc -I../../runtime/client/ -include rte_config.h -I$(DPDK_PATH)/include -O3 -g -mssse3 -o $@ $< \
		$(WRAPPERS) \
		$(DPDK_LIBS) $(STATIC_LIBS) -lnuma $(CFLAGS)

noiomgr_run: %: %.c ../../module/libwallet/libwallet.a
	gcc -I../libwallet/src/ -include rte_config.h -I$(DPDK_PATH)/include $< -O3 -march=znver3 -g -o $@ -L../libwallet/ -l:libwallet.a -lpthread -lnuma $(DPDK_LIBS) $(CFLAGS)

iomgr_run: %: %.c ../../module/libwallet/libwallet.a
	gcc -I../libwallet/src/ -include rte_config.h -I$(DPDK_PATH)/include $< -O3 -march=znver3 -g -o $@ -L../libwallet/ -l:libwallet.a -lpthread -lnuma $(DPDK_LIBS) $(CFLAGS)

iomgr_trustlet: %: %.c
	gcc -I../../runtime/client/ -include rte_config.h -I$(DPDK_PATH)/include -O3 -g -mssse3 -o $@ $< \
		$(WRAPPERS) \
		$(DPDK_LIBS) $(STATIC_LIBS) -lnuma $(CFLAGS)

insecure: insecure.c
	gcc -include rte_config.h -I$(DPDK_PATH)/include $< -O3 -march=znver3 -g -o $@ -lpthread -lnuma $(DPDK_LIBS) $(CFLAGS)

run_insecure: insecure
	make -C ../../ ssh_with_command SSH_COMMAND="cd module/example-dpdk && ./insecure --no-huge -l 0-$(CHAINING) --iova-mode=pa"

run_noiomgr: noiomgr_run noiomgr_trustlet
	make -C ../../ ssh_with_command SSH_COMMAND="cd module/example-dpdk && ./noiomgr_run"

simple_slick_fs: $(TRUSTLETS)
	mkdir -p ../../runtime/filesystem/simple/fs/lib/
	rm -rf ../../runtime/filesystem/simple/fs_out/
	rm -rf ../../runtime/filesystem/simple/fs/lib/*
	cp $(TRUSTLETS) ../../runtime/filesystem/simple/fs/lib/
	cp -L $(NUMA_LIB)/libnuma.so.1 ../../runtime/filesystem/simple/fs/lib/
	cp -L $(ATOMIC_LIB)/libatomic.so.1 ../../runtime/filesystem/simple/fs/lib/
	cp -L $(GLIBC_LIB)/libpthread.so.0 ../../runtime/filesystem/simple/fs/lib/
	cp -L $(GLIBC_LIB)/libm.so.6 ../../runtime/filesystem/simple/fs/lib/
	cd ../../runtime/filesystem/simple/; ./create.sh
