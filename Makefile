ROOT_PATH?=$(shell pwd)
MODULE_PATH?=${ROOT_PATH}/module/
KERNEL_PATH?=${ROOT_PATH}/linux/
KERNEL_PATCH?=${ROOT_PATH}/kernel.patch
USER?=$(shell whoami)
GUEST_PATH?=${ROOT_PATH}/tmp/
CORES?=1
MEM?=32

SOURCE_IMAGE=tmp
IMAGE_NAME=guest

FEATURE?=
LOG_LEVEL?="print"
BOOTTIME_ITERATION?=10

GRAMINE_BUILD?=release

IMAGE_SIZE=10
UBUNTU_IMAGE=https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
KERNEL_DIRS = kernel/linuxamd/ kernel/linux/ kernel/linux-guest/
CONFIG_FILES = $(addsuffix .config,$(KERNEL_DIRS))
USERADDR = $(shell expr $(shell id -u) % 1000)

REQUIREMENTS=requirements.txt

.PHONY: build_firmware setup_guest_net del_guest_net kvm unload_kvm load_kvm python run run_benchmark_sebs benchmark_sebs sebs_fs set_experiment_cold set_experiment_both

#Build OVMF Firmware
build_firmware:
	cd edk2/; PYTHON3_ENABLE=TRUE  PYTHON_COMMAND=python3 make -j16 -C BaseTools/
	cd edk2/; PYTHON3_ENABLE=TRUE  PYTHON_COMMAND=python3 source ./edksetup.sh; \
	PYTHON3_ENABLE=TRUE PYTHON_COMMAND=python3 build -a X64 -b RELEASE -t GCC5 -D DEBUG_ON_SERIAL_PORT -DTPM2_ENABLE -p OvmfPkg/OvmfPkgX64.dsc
	mkdir -p firmware
	cp edk2/Build/OvmfX64/RELEASE_GCC5/FV/OVMF* firmware/

clear_firmware_build:
	cd edk2/; git submodule foreach --recursive git clean -xfd
	cd edk2/; git clean -xfd

firmware/OVMF_CODE.fd: build_firmware
firmware/OVMF_VARS.fd: build_firmware

.PHONY: build_firmware setup_guest_net del_guest_net

VMPLkernel6.5.tar.gz: 
	-wget -nc https://github.com/TUM-DSE/svsm/releases/download/VMPL-guest-Image/VMPLkernel6.5.tar.gz
	tar -xvzf VMPLkernel6.5.tar.gz

images.tar.gz:
	-wget -nc https://github.com/TUM-DSE/Wallet-VMPL/releases/download/VMPL-Guest-Kernel/images.tar.gz
	cd module/; tar -xvzf ../images.tar.gz
#Get guest image
${SOURCE_IMAGE}.qcow2: VMPLkernel6.5.tar.gz
	-wget -nc ${UBUNTU_IMAGE} -O $@
    #rm ${IMAGE_NAME}.qcow2

#config: tmp.qcow2#
#	virt-copy-out -a tmp.qcow2 /boot/config-5.15.0-89-generic .
#	mv config-5.15.0-89-generic config


guest.qcow2: tmp.qcow2 scripts/build_image.sh build/linux/linux-headers-6.5.0-svsm.deb container/99_config.yaml
	(test -s ./guest.qcow2 && ./scripts/update_image.sh ${IMAGE_NAME} linux ) || bash ./scripts/build_image.sh tmp ${IMAGE_NAME} linux ${IMAGE_SIZE}


make update_guest:
	bash ./scripts/update_image.sh guest linux


linux/.config:
	cp config linux/.config

#Build container to build svsm kernel image
.buildcontainer: container/Dockerfile container/build.sh container/user.sh
	cd container; docker build -f Dockerfile -t vmplbuild .
	touch .buildcontainer

build/kernel/linux: linux/.config
	docker run -v ${shell pwd}:/mount -it vmplbuild bash -c "./user.sh $(shell id -g) $(shell id -u) linux"

setup_guest_net: #131.159.254.1
	sudo ip tuntap add tap0_${USER} mode tap
	sudo ip addr add 192.168.${USERADDR}.1/24 dev tap0_${USER}
	sudo ip link set up dev tap0_${USER}
	sudo iptables -t nat -A POSTROUTING -s 192.168.${USERADDR}.0/24 -j MASQUERADE

del_guest_net:
	sudo ip link delete tap0_${USER} || true

svsm/svsm.bin: build_svsm

SVSM_DEBUG?=enable-gdb


build_svsm:
	cd svsm; FW_FILE=../firmware/OVMF.fd make FEATURES="${SVSM_DEBUG} ${LOG_LEVEL} ${FEATURE}" RELEASE=True
node/bin/node:
	cd node; make
	cp node/bin/node module/

clean:
	git submodule foreach --recursive git clean -xfd
	cd node; make clean

submodules:
	git submodule update --init --recursive svsm;
	git submodule update --init --recursive edk2
	cd edk2; git submodule set-url -- UnitTestFrameworkPkg/Library/SubhookLib/subhook https://github.com/tianocore/edk2-subhook.git
	git submodule update --init --recursive edk2
	cd edk2; git apply ../patches/ovmf_outb.patch
	cd svsm/kernel/src/my_crypto/; ./build.sh
	git submodule update --init --recursive gramine-svsm;
	git submodule update --init --recursive Benchmarks/SeBS;

prepare_all: submodules build_svsm gramine guest.qcow2 setup_guest_net

initialize:
	git submodule update --init --recursive Benchmarks/SeBS
	git submodule update --init --recursive svsm
	cd svsm/kernel/src/my_crypto/; ./build.sh
	make build_svsm
	git submodule update --init --recursive gramine-svsm
	cd gramine-svsm; docker build -t gramine-build-container .
	make gramine
	cd scripts; ./sebs.sh one
	make kvm
	make unload_kvm
	make load_kvm
	make setup_guest_net
	make guest.qcow2
	chmod 0600 ./container/key

initialize_experiments: images.tar.gz
	git submodule update --init --recursive Benchmarks/CVM_eval
	cd Benchmarks/CVM_eval/; nix develop --command inv build.build-qemu-snp
	cd Benchmarks/CVM_eval/; nix develop --command inv build.build-ovmf-snp 
	cd Benchmarks/CVM_eval/; nix develop --command inv build.build-guest-fs-sebs
	cd Benchmarks/CVM_eval/; nix develop --command just setup-linux

guest_libs:
	cd scripts; ./setup.sh 192.168.${USERADDR}.10

build_and_run: build_svsm run

## Runs guest.qcow2 with SVSM
## Mounts ./module/ at /root/module 
run:
	sudo qemu-system-x86_64 \
	-enable-kvm \
	-cpu EPYC-v4,host-phys-bits=true  \
	-machine q35,confidential-guest-support=sev0,memory-backend=ram1 \
	-object memory-backend-memfd,id=ram1,size=${MEM}G,share=true \
	-object sev-snp-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,init-flags=4,igvm-file=svsm/bin/coconut-qemu.igvm \
	-smp ${CORES} \
	-no-reboot \
	-drive file=guest.qcow2,if=none,id=disk0,format=qcow2,snapshot=off \
	-device virtio-scsi-pci,id=scsi0,disable-legacy=on,iommu_platform=on \
	-device scsi-hd,drive=disk0,bootindex=0 \
	-netdev tap,ifname=tap0_${USER},id=net0,script=no,downscript=no -device e1000,netdev=net0 \
	-serial stdio \
	-serial pty \
	-virtfs local,path=module/,mount_tag=mo,security_model=passthrough \
	-virtfs local,path=Benchmarks/,mount_tag=benchmarks,security_model=passthrough \
	-virtfs local,path=gramine-svsm/,mount_tag=gramine,security_model=passthrough


ssh:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10

SSH_COMMAND?="shutdown"
ssh_with_command:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "${SSH_COMMAND}"

trustlet_test:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd module; make -B; insmod vmpl.ko; make -B t; ./test"

WARM_COLD?=wallet
run_benchmark_sebs:
	if [ "$(name)" == "110.dynamic-html" ]; then \
		cp module/libpal-html.so module/libpal.so; \
		cp module/libsysdb-html.so module/libsysdb.so; \
	elif [ "$(name)" == "120.uploader" ]; then \
	  	cp module/libpal-none.so module/libpal.so; \
		cp module/libsysdb-none.so module/libsysdb.so; \
	elif [ "$(name)" == "210.thumbnailer" ]; then \
	  	cp module/libpal-thumbnailer.so module/libpal.so; \
		cp module/libsysdb-thumbnailer.so module/libsysdb.so; \
	elif [ "$(name)" == "220.video-processing" ]; then \
	  	cp module/libpal-video.so module/libpal.so; \
		cp module/libsysdb-video.so module/libsysdb.so; \
	elif [ "$(name)" == "311.compression" ]; then \
	  	cp module/libpal-none.so module/libpal.so; \
		cp module/libsysdb-none.so module/libsysdb.so; \
	elif [ "$(name)" == "411.image-recognition" ]; then \
	  	cp module/libpal-image-recognition.so module/libpal.so; \
		cp module/libsysdb-image-recognition.so module/libsysdb.so; \
	elif [ "$(name)" == "501.graph-pagerank" ] || [ "$(name)" == "502.graph-mst" ] || [ "$(name)" == "503.graph-bfs" ]; then \
	  	cp module/libpal-igraph.so module/libpal.so; \
		cp module/libsysdb-igraph.so module/libsysdb.so; \
	elif [ "$(name)" == "504.dna-visualisation" ]; then \
	  	cp module/libpal-dna.so module/libpal.so; \
		cp module/libsysdb-dna.so module/libsysdb.so; \
	else \
	  	sleep 20; \
	  	echo "Wrong benchmark name."; \
	  	exit 1; \
	fi
	sleep 5
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "~/Benchmarks/sebs_script.sh $(name) ${WARM_COLD} && poweroff"

benchmark_sebs: run run_benchmark_sebs


container/99_config.yaml:
	./container/netconf.sh 2> /dev/null


kvm: 
	make -C host/ kvm

unload_kvm: 
	make -C host/ unload_kvm

load_kvm:
	make -C host/ load_kvm

copy_pal:
	cp gramine-svsm/build/pal/src/host/svsm/libpal.so module/

gramine:
	cd gramine-svsm; BUILD_MODE=${GRAMINE_BUILD} make build_external
	cp gramine-svsm/build/pal/src/host/svsm/libpal.so module/
	cp gramine-svsm/build/libos/src/libsysdb.so module/

python:
	git submodule update --init --recursive runtime/portable-python-cmake-buildsystem
	docker run --privileged -v ${PWD}/runtime:/build -it gramine-build-container make -C build/

simple_fs:
	mkdir -p runtime/filesystem/simple/fs/lib/
	cd runtime/filesystem/simple/src/; gcc -o ../fs/lib/nop nop.c
	cd runtime/filesystem/simple/src/; gcc -o ../fs/lib/helloworld helloworld.c
	cd runtime/filesystem/simple/src/; gcc -o ../fs/lib/cpuid cpuid.c
	cd Benchmarks/cow/; make -B cow; cp cow ../../runtime/filesystem/simple/fs/lib/
	cd runtime/filesystem/simple/; ./create.sh

IPC_BIN?=Benchmarks/IPC/wallet/com
simple_ipc_fs:
	mkdir -p runtime/filesystem/simple/fs/lib/
	rm -rf runtime/filesystem/simple/fs_out/
	rm -rf runtime/filesystem/simple/fs/lib/*
	make -B -C Benchmarks/IPC/wallet com
	cp ${IPC_BIN} runtime/filesystem/simple/fs/lib/com
	cd runtime/filesystem/simple/; ./create.sh

simple_latency_fs:
	mkdir -p runtime/filesystem/simple/fs/lib/
	rm -rf runtime/filesystem/simple/fs_out/
	rm -rf runtime/filesystem/simple/fs/lib/*
	make -B -C Benchmarks/IPC/wallet/extended 
	cp Benchmarks/IPC/wallet/extended/com_extended runtime/filesystem/simple/fs/lib/
	cd runtime/filesystem/simple/; ./create.sh

python_fs:
	mkdir -p runtime/filesystem/python/fs/lib
	mkdir -p runtime/filesystem/python/fs/python
	docker run --privileged -v ${PWD}/runtime:/build -it gramine-build-container make -C build/ python_fs
	cp ${REQUIREMENTS} runtime/requirements.txt
	make -C runtime/ prepare_python_libs
	rm runtime/requirements.txt
	cd runtime/filesystem/python; ./create.sh

simple_python_fs:
	mkdir -p runtime/filesystem/python/fs/lib
	mkdir -p runtime/filesystem/python/fs/python
	sudo rm -rf runtime/filesystem/python/fs/python/*
	sudo rm -rf runtime/filesystem/python/fs/lib/*
	sudo rm -rf runtime/filesystem/python/fs_out/
	echo "" > runtime/requirements.txt
	mkdir -p runtime/pip
	mv runtime/pip runtime/tmp_
	mkdir -p runtime/pip
	docker run --privileged -v ${PWD}/runtime:/build -it gramine-build-container make -C build/ python_fs
	make -C runtime/ prepare_python_libs
	cd runtime/filesystem/python; ./create.sh
	rm -r runtime/pip
	mv runtime/tmp_ runtime/pip

sebs_fs: python
	./scripts/sebs_fs.sh ${name}

boottime_setup:
	LOG_LEVEL="no_print" FEATURE="boottime" make build_svsm
	make run > /dev/null &
	sleep 30
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd module; make boottime_setup"
	make simple_python_fs
	make gramine
	LOG_LEVEL="no_print" FEATURE="boottime" make build_svsm
	cp module/libsysdb.so Benchmarks/Boottime/wallet/
	cp module/libpal.so Benchmarks/Boottime/wallet/

boottime_setup_vm:
	make run > /dev/null &
	sleep 20
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd module; make boottime_setup_vm"

ipc_setup:
	make simple_ipc_fs
	make gramine
	LOG_LEVEL="no_print" FEATURE="boottime" make build_svsm
	make run > /dev/null &
	sleep 30
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd module; make ipc_setup"
	cp module/libsysdb.so Benchmarks/IPC/wallet/
	cp module/libpal.so Benchmarks/IPC/wallet/

latency_setup:
	make simple_latency_fs
	make gramine
	cp module/libsysdb.so Benchmarks/IPC/wallet/extended/
	cp module/libsysdb.so Benchmarks/IPC/wallet/extended/


IPC_ITERATIONS?=5
IPC_SIZE?=64
ssh_ipc:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd Benchmarks/IPC/wallet/; python3 run.py ${IPC_SIZE} ${IPC_ITERATIONS} ${ZYGOTE_ID}"

ssh_alloc:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd Benchmarks/test/wallet/; python3 run.py ${IPC_SIZE} ${IPC_ITERATIONS}"

ipc:
	LOG_LEVEL="no_print" FEATURE="boottime prealloc" make build_svsm
	cd Benchmarks/IPC/wallet/; ./run.sh

shutdown:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "shutdown now"

boottime:
	LOG_LEVEL="no_print" FEATURE="boottime" make build_svsm
	cd Benchmarks/Boottime/wallet/; ITER=${BOOTTIME_ITERATION} ./run.sh
	cd Benchmarks/Boottime/wallet/; python parse_boottime.py > "no_prealloc.res"
	cp Benchmarks/Boottime/wallet/result.csv Benchmarks/Boottime/wallet/result_without_prealloc.csv

boottimes:
	cd Benchmarks/Boottime/; make native
	cd Benchmarks/Boottime/; make kata
	cd Benchmarks/Boottime/; make gramine

sebs_images:
	cd scripts/; ./sebs.sh

RESULT_PATH_PREALLOC ?= Benchmarks/SeBS_analysis/results/${WARM_COLD}_cow_prealloc
RESULT_PATH_NO_PREALLOC ?= Benchmarks/SeBS_analysis/results/${WARM_COLD}_cow_no_prealloc
TRACE_SEBS?=
STATS_SEBS?=
DISABLE_COW?=
run_sebs:
	mkdir -p ${RESULT_PATH_PREALLOC}
	mkdir -p ${RESULT_PATH_NO_PREALLOC}
	cd Benchmarks; ./run_sebs.sh "no_prealloc" "${RESULT_PATH_NO_PREALLOC}" "${WARM_COLD}" "${TRACE_SEBS}" "${STATS_SEBS}" "${DISABLE_COW}"
	cd Benchmarks; ./run_sebs.sh "prealloc" "${RESULT_PATH_PREALLOC}" "${WARM_COLD}" "${TRACE_SEBS}" "${STATS_SEBS}" "${DISABLE_COW}"

#################### SeBS Benchmark Setup ####################

set_experiment_cold:
	cat Benchmarks/SeBS/config/config_template.json | jq --args ".experiments.\"perf-cost\".experiments = [ \"cold\"]" > config.json
	mv config.json Benchmarks/SeBS/config/config_template.json

set_experiment_lukewarm:
	cat Benchmarks/SeBS/config/config_template.json | jq --args ".experiments.\"perf-cost\".experiments = [ \"sequential\"]" > config.json
	mv config.json Benchmarks/SeBS/config/config_template.json

set_experiment_both:
	cat Benchmarks/SeBS/config/config_template.json | jq --args ".experiments.\"perf-cost\".experiments = [ \"cold\", \"sequential\"]" > config.json
	mv config.json Benchmarks/SeBS/config/config_template.json

#################### SeBS Benchmarks ####################

BREAKDOWN_PATH=Benchmarks/SeBS_analysis/results/breakdown
run_sebs_breakdown:
	make set_experiment_cold
	cd Benchmarks; for pre in no_prealloc prealloc; do \
		for cow in cow no_cow; do \
			./run_sebs.sh $$pre "${BREAKDOWN_PATH}" "wallet" $$cow "breakdown" ;\
		done;\
	done;

BREAKDOWN_MEASURE_PATH=Benchmarks/SeBS_analysis/results/breakdown_measure
run_sebs_measure_breakdown:
	make set_experiment_cold
	cd Benchmarks; for cow in cow no_cow; do \
		./run_sebs.sh "prealloc" "${BREAKDOWN_MEASURE_PATH}" "wallet_extern" $$cow "breakdown" "measure" "external" ;\
	done;
	cp Benchmarks/SeBS_analysis/results/breakdown_measure/*/wallet*-*-prealloc-*cow Benchmarks/Boottime/breakdown/results/

SEBS_RESULT_PATH=Benchmarks/SeBS_analysis/results/SeBS
run_sebs_benchmark:
	make set_experiment_both
	cd Benchmarks; for pre in prealloc; do \
		for cow in cow no_cow; do \
			./run_sebs.sh $$pre "${SEBS_RESULT_PATH}" "wallet" $$cow "no_feature" "no_measure" ;\
		done;\
	done;

run_sebs_benchmark_lukewarm:
	make set_experiment_lukewarm
	cd Benchmarks; for pre in prealloc ; do \
		for cow in cow ; do \
			./run_sebs.sh $$pre "${SEBS_RESULT_PATH}" "wallet_warm" $$cow "no_feature" "no_measure" ;\
		done; \
	done;

SEBS_MEASURE_RESULT_PATH=Benchmarks/SeBS_analysis/results/SeBS_measure
run_sebs_measure_benchmark:
	make set_experiment_both
	cd Benchmarks; for cow in no_cow cow ; do \
		./run_sebs.sh "prealloc" "${SEBS_MEASURE_RESULT_PATH}" "wallet" $$cow "no_feature" "measure" ;\
	done;

run_sebs_measure_benchmark_lukewarm:
	make set_experiment_both
	cd Benchmarks; for cow in cow ; do \
		./run_sebs.sh "prealloc" "${SEBS_MEASURE_RESULT_PATH}" "wallet_warm" $$cow "no_feature" "measure" ;\
	done;


SEBS_PROFILING_MEASURE_RESULT_PATH=Benchmarks/SeBS_analysis/results/measure_profiling
run_sebs_measure_profiling:
	make set_experiment_cold
	cd Benchmarks; for cow in no_cow cow; do \
		./run_sebs.sh "prealloc" "${SEBS_PROFILING_MEASURE_RESULT_PATH}" "wallet_profiling" $$cow "stat" "measure" ;\
	done;

SEBS_PROFILING_RESULT_PATH=Benchmarks/SeBS_analysis/results/profiling
run_sebs_profiling:
	make set_experiment_cold
	cd Benchmarks; for cow in no_cow cow; do \
		./run_sebs.sh "prealloc" "${SEBS_PROFILING_RESULT_PATH}" "wallet_profiling" $$cow "stat" "measure" ;\
	done;

SEBS_EXTERN_RESULT_PATH=Benchmarks/SeBS_analysis/results/SeBS_extern
run_sebs_external_benchmark:
	make set_experiment_both
	cd Benchmarks; for cow in cow; do \
		for pre in prealloc; do \
			./run_sebs.sh $$pre ${SEBS_EXTERN_RESULT_PATH} "wallet_extern" $$cow "no_feature" "no_measure" "external" ;\
		done; \
	done;

SEBS_EXTERN_LUKEWARM_RESULT_PATH=Benchmarks/SeBS_analysis/results/SeBS_extern_warm
run_sebs_external_lukewarm_benchmark:
	make set_experiment_lukewarm
	cd Benchmarks; for cow in cow; do \
		for pre in prealloc; do \
			./run_sebs.sh $$pre ${SEBS_EXTERN_LUKEWARM_RESULT_PATH} "wallet_extern" $$cow "no_feature" "no_measure" "external" ;\
		done; \
	done;

SEBS_MEMORY_EXTERN_RESULT_PATH=Benchmarks/SeBS_analysis/results/memory_extern
run_sebs_measure_profiling_extern:
	make set_experiment_cold
	cd Benchmarks/SeBS/; git apply ../../patches/wallet_memory.patch
	cd Benchmarks; for cow in cow; do \
                ./run_sebs.sh "prealloc" "${SEBS_MEMORY_EXTERN_RESULT_PATH}" "wallet_extern" $$cow "stat" "measure" "external" ;\
        done;
	cd Benchmarks/SeBS/; git apply -R ../../patches/wallet_memory.patch


#### End-to-End 

run_sebs_wallet:
	cd Benchmarks/SeBS; git apply -R ../../patches/wallet_cold.patch
	make run_sebs_external_lukewarm_benchmark
	cp -r Benchmarks/SeBS_analysis/results/SeBS_extern_warm/wallet_extern_cow_prealloc/* Benchmarks/SeBS_analysis/results/wallet_warm_cow_prealloc/
	cd Benchmarks/SeBS; git apply ../../patches/wallet_cold.patch
	make run_sebs_external_benchmark
	cp -r Benchmarks/SeBS_analysis/results/SeBS_extern_warm/wallet_extern_cow_prealloc/* Benchmarks/SeBS_analysis/results/wallet_cow_prealloc/


RESULT_TARGET?=gramine

move_result:
	sudo rm -r Benchmarks/SeBS_analysis/results/${RESULT_TARGET}/*
	cd Benchmarks/CVM_eval/benchmarks/sebs/SeBS/; mv -f \
		110.dynamic-html \
		210.thumbnailer \
		311.compression \
		411.image-recognition \
		501.graph-pagerank \
		502.graph-mst \
		503.graph-bfs \
		504.dna-visualisation \
		../../../../SeBS_analysis/results/${RESULT_TARGET}/
run_sebs_gramine:
	make set_experiment_both
	cd Benchmarks; ./sebs_script_non_wallet.sh gramine
	make move_result RESULT_TARGET=gramine

run_sebs_native:
	make set_experiment_both
	cd Benchmarks; ./sebs_script_non_wallet.sh native
	make move_result RESULT_TARGET=native

run_sebs_kata:
	make set_experiment_both
	cd Benchmarks; ./sebs_script_non_wallet.sh kata_qemu
	make move_result RESULT_TARGET=kata

run_sebs_vm:
	make set_experiment_both
	cd Benchmarks/CVM_eval/benchmarks/sebs/SeBS; git apply ../../../../../patches/sebs_vm.patch 
	cd Benchmarks/CVM_eval; nix develop --command bash -c "cd ../; ./sebs_script_non_wallet.sh cvm"
	make move_result RESULT_TARGET=vm
	cd Benchmarks/CVM_eval/benchmarks/sebs/SeBS; git apply -R ../../../../../patches/sebs_vm.patch

run_sebs_cvm:
	make set_experiment_both
	cd Benchmarks/CVM_eval; nix develop --command bash -c "cd ../; ./sebs_script_non_wallet.sh cvm"
	make move_result RESULT_TARGET=cvm

END_TO_END_PATH=Benchmarks/SeBS_analysis/output
END_TO_END_FIGURE=${END_TO_END_PATH}/client_time_side_by_side_lukewarm_log.pdf

${END_TO_END_FIGURE}:
	cd Benchmarks/SeBS_analysis; python plot.py

plot_end_to_end: ${END_TO_END_FIGURE}
	mkdir -p figures/
	cp ${END_TO_END_PATH}/client_time_side_by_side_lukewarm_log.pdf figures/figure7.pdf

figures/figure8a.pdf: ${END_TO_END_FIGURE}
	cp ${END_TO_END_PATH}/invocation_latency_cdf_with_lukewarm_linear.pdf figures/figure8a.pdf

plot_invocation_latency: figures/figure8a.pdf

#### Breakdown

BREAKDOWN_PATH=Benchmarks/Boottime/breakdown

Benchmarks/Boottime/breakdown/breakdown_results.csv:
	make run_sebs_measure_breakdown
	mkdir -p ${BREAKDOWN_PATH}/measure
	cp ${BREAKDOWN_PATH}/results/wallet_extern* ${BREAKDOWN_PATH}/measure
	cd ${BREAKDOWN_PATH}; python measure_parse.py > breakdown_results.csv

run_sebs_wallet_breakdown: ${BREAKDOWN_PATH}/breakdown_results.csv

${BREAKDOWN_PATH}/output/runtime_init_linear_time_all.pdf:
	cd ${BREAKDOWN_PATH}; python plot.py breakdown_results.csv

figures/figure8b.pdf: ${BREAKDOWN_PATH}/output/runtime_init_linear_time_all.pdf
	cp ${BREAKDOWN_PATH}/output/runtime_init_linear_time_all.pdf figures/figure8b.pdf

plot_runtime_breakdown: ${BREAKDOWN_PATH}/breakdown_results.csv figures/figure8b.pdf

#### Memory

run_sebs_wallet_memory: run_sebs_measure_profiling_extern

Benchmarks/SeBS_analysis/output/wallet_memory_usage_comparison.pdf:
	cd Benchmarks/SeBS_analysis/; python parse_traces.py memory
	cd Benchmarks/SeBS_analysis/; python plot_memory.py

figure/figure8c.pdf: Benchmarks/SeBS_analysis/output/wallet_memory_usage_comparison.pdf
	cp Benchmarks/SeBS_analysis/output/wallet_memory_usage_comparison.pdf figures/figure8c.pdf

plot_memory_usage: figure/figure8c.pdf

#### Communication latency

Benchmarks/IPC/extended/results.csv:
	printf "chain_length,size,time\n" > Benchmarks/IPC/extended/results.csv

run_comm_latency_kata: Benchmarks/IPC/extended/results.csv
	cd Benchmarks/IPC/extended/; ./run.sh kata &> /dev/null

run_comm_latency_vm: Benchmarks/IPC/extended/results.csv
	cd Benchmarks/IPC/extended/; ./run.sh VM &> /dev/null

run_comm_latency_cvm: Benchmarks/IPC/extended/results.csv
	cd Benchmarks/IPC/extended/; ./run.sh CVM &> /dev/null

run_comm_latency_wallet:
	make latency_setup
	LOG_LEVEL="no_print" SVSM_DEBUG="" FEATURE="boottime prealloc" make build_svsm &> /dev/null
	cd Benchmarks/IPC/wallet/extended/; ./run.sh 
	cat Benchmarks/IPC/wallet/extended/result.csv > Benchmarks/IPC/extended/results.csv

Benchmarks/IPC/output/IPC_chain_linear.pdf:
	cd Benchmarks/IPC/; python ipc_chain_plot.py extended/results.csv

figures/figure9.pdf: Benchmarks/IPC/output/IPC_chain_linear.pdf
	cp Benchmarks/IPC/output/IPC_chain_linear.pdf figures/figure9.pdf

plot_comm_latency: figures/figure9.pdf
#### Simulation

AzureTraces/invitro/wallet_traces/wallet_traces_4000/function_invocations.csv:
	git submodule update --init --recursive AzureTraces/invitro || \
		(mkdir -p AzureTraces/invitro/wallet_traces/; cp -r /scratch/${USER}/wallet_traces/* AzureTraces/invitro/wallet_traces/)

AzureTraces/wallet4000_prepared.csv: AzureTraces/invitro/wallet_traces/wallet_traces_4000/function_invocations.csv
	cd AzureTraces; python3 preprocess.py invitro/wallet_traces/wallet_traces_4000/function_invocations.csv wallet4000_prepared.csv

AzureTraces/simulation_results_parallel_100.txt: AzureTraces/wallet4000_prepared.csv
	cd AzureTraces; python sim_node_scalability.py wallet4000_prepared.csv
	cp AzureTraces/simulation_results_parallel.txt AzureTraces/simulation_results_parallel_100.txt

AzureTraces/simulation_results_parallel_5.txt: AzureTraces/wallet4000_prepared.csv
	git apply patches/motivation_simulation.patch
	cd AzureTraces; python sim_node_scalability.py wallet4000_prepared.csv
	cp AzureTraces/simulation_results_parallel.txt AzureTraces/simulation_results_parallel_5.txt
	git apply -R patches/motivation_simulation.patch

run_simulation: AzureTraces/simulation_results_parallel_100.txt AzureTraces/simulation_results_parallel_5.txt

plot_simulation: AzureTraces/simulation_results_parallel_100.txt AzureTraces/simulation_results_parallel_5.txt 
	cd Benchmarks/Simulation_analysis/; python plot_simulation_CDF.py ../../AzureTraces/simulation_results_parallel_100.txt
	mkdir -p figures
	cp Benchmarks/Simulation_analysis/output/pdf/simulation_results_parallel_node_size_100_delays_log.pdf figures/figure10a.pdf
	cp Benchmarks/Simulation_analysis/output/pdf/simulation_results_parallel_node_size_100_slowdowns_log.pdf figures/figure10b.pdf
	cp Benchmarks/Simulation_analysis/output/pdf/simulation_results_parallel_percentile_delay_nodes.pdf figures/figure10c.pdf
	cd Benchmarks/Simulation_analysis/; python motivation_plot_simulation_CDF.py ../../AzureTraces/simulation_results_parallel_5.txt
	cp Benchmarks/Simulation_analysis/output/pdf/simulation_results_parallel_node_size_5_delays_log.pdf figures/figure2a.pdf

plot_cdf_motivation:
	cd Benchmarks/Simulation_analysis/; python motivation_plot_simulation_CDF.py ../../AzureTraces/simulation_results_parallel_5.txt
	mkdir -p figures
	cp Benchmarks/Simulation_analysis/output/pdf/simulation_results_parallel_node_size_5_delays_log.pdf figures/figure2a.pdf

##### Attestation

plot_attest_motivation:
	cd Benchmarks/Attestation/; python3 plot_breakdown.py --csv_file results.csv
	mkdir -p figures/
	cp Benchmarks/Attestation/output/attestation_breakdown_cutoff.pdf figures/figure2c.pdf

#### Scaling

SCALE=cd Benchmarks/scale; python3 run.py
LIMIT_INCREASE=sudo prlimit --pid=$$$$ --nofile=1000000

run_scale_kata:
	@${LIMIT_INCREASE};${SCALE} kata &> /dev/null
	@reset

run_scale_vm:
	@${LIMIT_INCREASE};${SCALE} vm &> /dev/null
	@reset

run_scale_cvm:
	@${LIMIT_INCREASE};${SCALE} cvm &> /dev/null
	@reset

run_scale_wallet:
	@#See Benchmarks/scale/README.md
	@test -f Benchmarks/scale/result.csv || \
	        printf "type,instances,assigned_memory,memory_usage,shared_pages\n" > Benchmarks/scale/result.csv
	@for n in 1 100 200 300 400 500 600 700; do\
	        printf "wallet,%d,0.5,%d,0\n" $$n $$(expr 37755 \* 4096 +  $$n \* 15 \* 4096) >> Benchmarks/scale/result.csv; \
	done

plot_scaling_motivation:
	cd Benchmarks/scale; python3 plot.py result.csv
	mkdir -p figures/
	cp Benchmarks/scale/output/function_density_linear.pdf figures/figure2b.pdf

#### Boottime

BOOTPATH=Benchmarks/Boottime

run_boottime_native:
	cd ${BOOTPATH}; make native

run_boottime_kata:
	cd ${BOOTPATH}; make kata

run_boottime_gramine:
	cd ${BOOTPATH}; make gramine

run_boottime_vm:
	cd ${BOOTPATH}; make vm

run_boottime_cvm:
	cd ${BOOTPATH}; make cvm

run_boottime_wallet:
	cp guest.qcow2 guest.qcow2_bak
	make boottime_setup
	make boottime
	cp guest.qcow2_bak guest.qcow2

plot_boottime_motivation:
	cd ${BOOTPATH}; \
		cat wallet/no_prealloc.res > results.txt; \
		echo "" >> results.txt; \
		cat vm_result.txt >> results.txt; \
		echo "" >> results.txt; \
		cat cvm_result.txt >> results.txt; \
		echo "" >> results.txt; \
		cat kata/result.txt >> results.txt; \
		echo "" >> results.txt; \
		cat gramine/result.txt >> results.txt; \
		echo "" >> results.txt; \
		cat native/result.txt >> results.txt; 
	cd ${BOOTPATH}; \
		python plot.py results.txt
	mkdir -p figures
	cp ${BOOTPATH}/output/boot_time_cutoff.pdf figures/figure1a.pdf

#### Prepair

prepair_vm:
	make build_svsm
	make run > /dev/null &
	sleep 50
	SSH_COMMAND="cd module; make vmpl.ko; insmod vmpl.ko" make ssh_with_command
	SSH_COMMAND="cd module; make -B -C libwallet/ libwallet.so libwallet.a" make ssh_with_command
	SSH_COMMAND="cd module/python; python3 setup.py install" make ssh_with_command
	SSH_COMMAND="cd module/example; python3 test.py" make ssh_with_command
	SSH_COMMAND="shutdown now" make ssh_with_command

#### Communication

COMMPATH=Benchmarks/IPC
COMMPLOTPATH=Benchmarks/Communication_cost

run_comm_wallet:
	cp guest.qcow2 guest.qcow2_bak
	make ipc_setup
	make ipc &> /dev/null 
	cp guest.qcow2_bak guest.qcow2

run_comm_vm:
	cd ${COMMPATH}; ./run.sh VM

run_comm_cvm:
	cd ${COMMPATH}; ./run.sh CVM

run_comm_kata:
	cd ${COMMPATH}; ./run.sh kata

run_comm_gramine:
	cd ${COMMPATH}/gramine; make
	cd ${COMMPATH}/gramine; ./gramine.sh
	cd ${COMMPATH}/gramine; python parse.py gramine

run_comm_native:
	cd ${COMMPATH}/native; make
	cd ${COMMPATH}/native; ./native.sh || true
	cd ${COMMPATH}/native; python parse.py native pipe

plot_comm_motivation:
	cd ${COMMPATH}; \
		echo "Wallet:" > results.txt; \
		cat wallet/res.csv >> results.txt; \
		echo "" >> results.txt; \
		cat vm_result.txt >> results.txt; \
		cat cvm_result.txt >> results.txt; \
		cat kata_result.txt >> results.txt; \
		echo "Gramine:" >> results.txt; \
		cat gramine/res_gramine.csv >> results.txt; \
		echo "" >> results.txt; \
		echo "Native:" >> results.txt; \
		cat native/res_native_pipe.csv >> results.txt
	cd ${COMMPATH}; cp results.txt ../Communication_cost/
	cd ${COMMPLOTPATH}; python plot.py results.txt
	mkdir -p figures
	cp ${COMMPLOTPATH}/output/IPC_log.pdf figures/figure1b.pdf


#### Execute all benchmarks

LOCK_FILE=/tmp/wallet_benchmark.lock

lock:
	echo ${USER} > ${LOCK_FILE}

unlock:
	rm -f ${LOCK_FILE}

run_all:
	@make lock
	make _run_all_ || make unlock
	@make unlock

run_all_cvm:
	@make lock
	make _run_all_cvm_ || make unlock
	@make unlock

_run_all_:
	@#Setup
	@mkdir -p steps/logs
	@echo "Starting Initialization $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/init ]]; then \
		rm -r guest.qcow2 &> steps/logs/init; \
		make del_guest_net &>> steps/logs/init; \
		make initialize &>> steps/logs/init; \
		make prepair_vm &>> steps/logs/init; \
		make initialize_experiments &>> steps/logs/init; \
		touch steps/init; \
	else \
		make del_guest_net &>> steps/logs/init; \
		make setup_guest_net &>> steps/logs/init; \
		make kvm &>> steps/logs/init; \
		make unload_kvm &>> steps/logs/init; \
		make load_kvm &>> steps/logs/init; \
	fi
	@echo "Initialization completed"
	@echo "Starting Benchmarks $$(date +"%H:%M:%S")"
	@echo "Starting end to end Benchmarks"
	@if [[ ! -f steps/end_to_end ]]; then \
		make run_sebs_wallet &> steps/logs/end_wallet;\
		make run_sebs_vm &> steps/logs/end_vm; \
		make run_sebs_kata &> steps/logs/end_kata; \
		make run_sebs_gramine &> steps/logs/end_gramine; \
		make run_sebs_native &> steps/logs/end_native; \
		make plot_end_to_end &> steps/logs/end_plot; \
		make plot_invocation_latency &>> steps/logs/end_plot; \
	fi
	@echo "Starting runtime Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/breakdown ]]; then \
		make run_sebs_wallet_breakdown &> steps/logs/breakdown; \
		make plot_runtime_breakdown &> steps/logs/breakdown_plot; \
		touch steps/breakdown; \
	fi
	@echo "Starting memory Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/memory ]]; then \
		make run_sebs_wallet_memory &> steps/logs/memory; \
		make plot_memory_usage &> steps/logs/memory_plot; \
		touch steps/memory; \
	fi
	@echo "Starting communication latency Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/comm_latency ]]; then \
		make run_comm_latency_wallet &> steps/logs/lat_wallet; \
		make run_comm_latency_kata &> steps/logs/lat_kata; \
		make run_comm_latency_vm &> steps/logs/lat_vm; \
		make run_comm_latency_cvm &> steps/logs/lat_cvm; \
		make plot_comm_latency &> steps/logs/lat_plot; \
		touch steps/comm_latency; \
	fi
	@echo "Starting Simulation $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/simulation ]]; then \
		make run_simulation &> steps/logs/sim; \
		make plot_simulation &> steps/logs/sim_plot; \
		make plot_cdf_motivation &> steps/logs/sim_mot_plot; \
		touch steps/simulation; \
	fi
	@echo "Starting boottime Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/boottime ]]; then \
		make run_boottime_native &> steps/logs/boot_native; \
		make run_boottime_kata &> steps/logs/boot_kata; \
		make run_boottime_gramine &> steps/logs/boot_gramine; \
		make run_boottime_wallet &> steps/logs/boot_wallet; \
		make run_boottime_vm &> steps/logs/boot_vm; \
		make plot_boottime_motivation &> steps/logs/boot_plot; \
		touch steps/boottime; \
	fi
	@echo "Starting communicaton Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/comm ]]; then \
		make run_comm_native &> steps/logs/comm_native; \
		make run_comm_gramine &> steps/logs/comm_gramine; \
		make run_comm_kata &> steps/logs/comm_kata; \
		make run_comm_vm &> steps/logs/comm_vm; \
		make run_comm_cvm &> steps/logs/comm_cvm; \
		make run_comm_wallet &> steps/logs/comm_wallet; \
		make plot_comm_motivation &> steps/logs/comm_plot; \
		touch steps/comm; \
	fi
	@echo "Starting scale Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/scale ]]; then \
		make run_scale_vm &> steps/logs/scale_vm; \
		make run_scale_kata &> steps/logs/scale_kata; \
		make run_scale_wallet &> steps/logs/scale_wallet; \
		touch steps/scale; \
	fi
	@echo "Finishng plots $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/plot ]]; then \
		make plot_attest_motivation &> steps/logs/att_plot; \
		make plot_scaling_motivation &> steps/logs/scale_plot; \
		touch steps/plot;
	fi
	@echo "Done"

_run_all_cvm_:
	@#Setup
	@mkdir -p steps/logs
	@echo "Starting Initialization $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/init ]]; then \
                rm -r guest.qcow2 &> steps/logs/init; \
                make initialize_experiments &>> steps/logs/init; \
                touch steps/init; \
        fi
	@echo "Starting end to end Benchmarks $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/end_to_end ]]; then \
		make run_sebs_cvm &> steps/logs/end_cvm; \
		touch steps/end_to_end; \
	fi
	@echo "Starting boottime Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/boottime ]]; then \
		make run_boottime_cvm &> steps/logs/boot_cvm; \
		touch steps/boottime; \
	fi
	@echo "Starting scale Benchmark $$(date +"%H:%M:%S")"
	@if [[ ! -f steps/scale ]]; then \
		make run_scale_cvm &> steps/logs/scale_cvm; \
		touch steps/scale; \
	fi
	@echo "Done"

ifeq ($(wildcard ${LOCK_FILE}),)
NOLOCK=1
else
LOCK=1
endif
ifeq ($(shell cat ${LOCK_FILE}),${USER})
USERMATCH=1
endif

ifdef LOCK
	ifndef USERMATCH
		$(error Lock file is engage. User $(shell cat ${LOCK_FILE}) is running a benchmark since $(shell date -r ${LOCK_FILE}). If this is not the case please delete ${LOCK_FILE}.)
	endif
endif

