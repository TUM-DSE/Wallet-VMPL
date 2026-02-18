TRUSTLET_SRCS := $(wildcard *_trustlet.c)
TRUSTLETS := $(TRUSTLET_SRCS:.c=)
RUNNER_SRCS := $(wildcard *_run.py)
RUNNERS := $(RUNNER_SRCS:.py=)
C_RUNNER_SRCS := $(wildcard *_run.c)
C_RUNNERS := $(C_RUNNER_SRCS:.c=)



all: $(TRUSTLETS)

run_tests:
	@for runner in $(RUNNERS); do \
		echo "Running $$runner..."; \
		make $$runner; \
	done
	@for c_runner in $(C_RUNNERS); do \
		echo "Running $$c_runner..."; \
		make $$c_runner; \
	done
	# make -C ../../ trustlet_test

$(RUNNERS): %: %.py
	make -C ../../ ssh_with_command SSH_COMMAND="cd module/example-tests && python3 $<"

DPDK_PATH := /nix/store/hjrh0kinf6bz444r0s5rw557gjswxwnx-dpdk-23.11
# DPDK_PATH := /scratch/okelmann/dpdk/build
GLIBC_STATIC := /nix/store/24hs0bbh26w5zfvkv5ps2amfrbwnz8pd-glibc-2.40-66-static/lib
DPDK_LIBS := -Wl,--whole-archive \
	$(DPDK_PATH)/lib/librte_eal.a \
	$(DPDK_PATH)/lib/librte_ring.a \
	$(DPDK_PATH)/lib/librte_log.a \
	$(DPDK_PATH)/lib/librte_kvargs.a \
	$(DPDK_PATH)/lib/librte_telemetry.a \
	$(DPDK_PATH)/lib/librte_mempool.a \
	$(DPDK_PATH)/lib/librte_mbuf.a \
	-Wl,--no-whole-archive
STATIC_LIBS := -Wl,--whole-archive $(GLIBC_STATIC)/libpthread.a $(GLIBC_STATIC)/libdl.a -Wl,--no-whole-archive
WRAPPERS := -Wl,--wrap=rte_zmalloc -Wl,--wrap=rte_memzone_reserve_aligned

$(TRUSTLETS): %: %.c
	gcc -I../../runtime/client/ -include rte_config.h -I$(DPDK_PATH)/include -o $@ $< \
		$(WRAPPERS) \
		$(DPDK_LIBS) $(STATIC_LIBS) -lnuma

$(C_RUNNERS): %: %.c ../../module/libwallet/libwallet.a # compile in guest
	make -C ../../ ssh_with_command SSH_COMMAND="cd module/example-tests && gcc -I../../module/libwallet/src/ -include rte_config.h -I/usr/include/dpdk -I/usr/include/x86_64-linux-gnu/dpdk $< -O3 -march=native -g -o $@ $(WRAPPERS) -L../../module/libwallet/ -l:libwallet.a -lpthread -lrte_eal -lrte_ring -lrte_mempool -lrte_mbuf"
	make -C ../../ ssh_with_command SSH_COMMAND="cd module/example-tests && ./$@"

NUMA_LIB := /nix/store/557rbsz8mbv0w97gw8v2ni7x9d40x509-numactl-2.0.18/lib
ATOMIC_LIB := /nix/store/f1ii69v7p27z1r5zybmlbld3bdzm6a5f-gcc-13.2.0-lib/lib
GLIBC_LIB := /nix/store/35pq4hr29c3sl79lgfwgsvd9nwzyp4am-glibc-2.39-5/lib

simple_slick_fs: $(TRUSTLETS)
	mkdir -p ../../runtime/filesystem/simple/fs/lib/
	rm -rf ../../runtime/filesystem/simple/fs_out/
	rm -rf ../../runtime/filesystem/simple/fs/lib/*
	cp $(TRUSTLETS) ../../runtime/filesystem/simple/fs/lib/
	cp -L $(NUMA_LIB)/libnuma.so.1 ../../runtime/filesystem/simple/fs/lib/
	cp -L $(ATOMIC_LIB)/libatomic.so.1 ../../runtime/filesystem/simple/fs/lib/
	cp -L $(GLIBC_LIB)/libpthread.so.0 ../../runtime/filesystem/simple/fs/lib/
	cd ../../runtime/filesystem/simple/; ./create.sh

clean:
	rm -f $(TRUSTLETS) $(C_RUNNERS)


.PHONY: all clean $(RUNNERS) $(C_RUNNERS)
