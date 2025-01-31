ROOT_PATH?=$(shell pwd)
MODULE_PATH?=${ROOT_PATH}/module/
KERNEL_PATH?=${ROOT_PATH}/linux/
KERNEL_PATCH?=${ROOT_PATH}/kernel.patch
USER?=$(shell whoami)
GUEST_PATH?=${ROOT_PATH}/tmp/
CORES?=1

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
USERADDR = $(shell expr $(shell id -u) - 1000)

REQUIREMENTS=requirements.txt

.PHONY: build_firmware setup_guest_net del_guest_net kvm unload_kvm load_kvm python run run_benchmark_sebs benchmark_sebs sebs_fs

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
	sudo iptables -t nat -A POSTROUTING -o enp2s0f0np0 -j MASQUERADE

del_guest_net:
	sudo ip link delete tap0_${USER}
	sudo iptables -t nat -D POSTROUTING -o enp2s0f0np0 -j MASQUERADE
	echo ""

svsm/svsm.bin: build_svsm

build_svsm:
	cd svsm; FW_FILE=../firmware/OVMF.fd make FEATURES="enable-gdb ${FEATURE} ${LOG_LEVEL}" RELEASE=True
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

build_and_run: build_svsm run

## Runs guest.qcow2 with SVSM
## Mounts ./module/ at /root/module 
run:
	sudo qemu-system-x86_64 \
	-enable-kvm \
	-cpu EPYC-v4,host-phys-bits=true  \
	-machine q35,confidential-guest-support=sev0,memory-backend=ram1 \
	-object memory-backend-memfd,id=ram1,size=8G,share=true \
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

trustlet_test:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd module; make -B; insmod vmpl.ko; make -B t; ./test"


run_benchmark_sebs:
	if [ "$(name)" == "110.dynamic-html" ]; then \
  		cp module/libpal-html.so module/libpal.so; \
  		cp module/libsysdb-html.so module/libsysdb.so; \
	elif [ "$(name)" == "210.thumbnailer" ]; then \
	  	cp module/libpal-thumbnailer.so module/libpal.so; \
		cp module/libsysdb-thumbnailer.so module/libsysdb.so; \
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
	sleep 20
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "~/Benchmarks/sebs_script.sh $(name) && poweroff"

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
	cd runtime/filesystem/simple/; ./create.sh

IPC_BIN?=Benchmarks/IPC/wallet/com
simple_ipc_fs:
	mkdir -p runtime/filesystem/simple/fs/lib/
	rm -rf runtime/filesystem/simple/fs_out/
	rm -rf runtime/filesystem/simple/fs/lib/*
	make -B -C Benchmarks/IPC/wallet com
	cp ${IPC_BIN} runtime/filesystem/simple/fs/lib/com
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
	sudo rm -rf runtime/filesystem/sebs/fs/lib
	# sudo rm -rf runtime/filesystem/sebs/fs/python
	mkdir -p runtime/filesystem/sebs/fs/lib
	mkdir -p runtime/filesystem/sebs/fs/python

	# make python deps and prepare stdlib, libcpuid
	docker run --privileged -v ${PWD}/runtime:/build -it gramine-build-container make -C build/ sebs_fs
	make -C runtime/ libcpuid.so

	# prepare pip
	if [ ! -d runtime/filesystem/sebs/pip ]; then \
  		pip install --target=runtime/filesystem/sebs/pip/110/ -r Benchmarks/SeBS/benchmarks/100.webapps/110.dynamic-html/python/requirements.txt; \
  		pip install --target=runtime/filesystem/sebs/pip/210/ -r Benchmarks/SeBS/benchmarks/200.multimedia/210.thumbnailer/python/requirements.txt.3.11; \
  		pip install --target=runtime/filesystem/sebs/pip/411/ -r Benchmarks/SeBS/benchmarks/400.inference/411.image-recognition/python/requirements.txt.3.11; \
  		pip install --target=runtime/filesystem/sebs/pip/501/ -r Benchmarks/SeBS/benchmarks/500.scientific/501.graph-pagerank/python/requirements.txt.3.11; \
  		pip install --target=runtime/filesystem/sebs/pip/504/ -r Benchmarks/SeBS/benchmarks/500.scientific/504.dna-visualisation/python/requirements.txt; \
  	fi

	rm -r runtime/filesystem/sebs/fs/dependencies || true
	cd runtime/filesystem/sebs; \
	if [ "$(name)" == "110.dynamic-html" ]; then \
  		while IFS= read -r file; do \
            if [ -e "pip/110/$$file" ]; then \
                mkdir -p "fs/dependencies/$$(dirname "$$file")"; \
                cp "pip/110/$$file" "fs/dependencies/$$(dirname "$$file")"; \
            else \
                echo "File pip/110/$$file does not exist"; \
            fi \
        done < "pip/110.txt"; \
        \
        cp ../../../Benchmarks/SeBS/benchmarks/100.webapps/110.dynamic-html/python/templates/template.html fs/dependencies; \
	elif [ "$(name)" == "210.thumbnailer" ]; then \
  		while IFS= read -r file; do \
            if [ -e "pip/210/$$file" ]; then \
                mkdir -p "fs/dependencies/$$(dirname "$$file")"; \
                cp "pip/210/$$file" "fs/dependencies/$$(dirname "$$file")"; \
            else \
                echo "File pip/210/$$file does not exist"; \
            fi \
        done < "pip/210.txt"; \
	elif [ "$(name)" == "411.image-recognition" ]; then \
  		while IFS= read -r file; do \
            if [ -e "pip/411/$$file" ]; then \
                mkdir -p "fs/dependencies/$$(dirname "$$file")"; \
                cp "pip/411/$$file" "fs/dependencies/$$(dirname "$$file")"; \
            else \
                echo "File pip/411/$$file does not exist"; \
            fi \
        done < "pip/411.txt"; \
        \
        cp ../../../Benchmarks/SeBS/benchmarks/400.inference/411.image-recognition/python/imagenet_class_index.json fs/dependencies; \
        \
        cp ../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/libdl.so.2 fs/lib; \
        cp ../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/librt.so.1 fs/lib; \
        docker run --privileged -v $${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libstdc++.so.6 /build/fs/lib/; \
        docker run --privileged -v $${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libgcc_s.so.1 /build/fs/lib/; \
	elif [ "$(name)" == "501.graph-pagerank" ] || [ "$(name)" == "502.graph-mst" ] || [ "$(name)" == "503.graph-bfs" ]; then \
  		while IFS= read -r file; do \
            if [ -e "pip/501/$$file" ]; then \
                mkdir -p "fs/dependencies/$$(dirname "$$file")"; \
                cp "pip/501/$$file" "fs/dependencies/$$(dirname "$$file")"; \
            else \
                echo "File pip/501/$$file does not exist"; \
            fi \
        done < "pip/501.txt"; \
        \
        cp ../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/libdl.so.2 fs/lib; \
        docker run --privileged -v $${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libstdc++.so.6 /build/fs/lib/; \
        docker run --privileged -v $${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libgcc_s.so.1 /build/fs/lib/; \
	elif [ "$(name)" == "504.dna-visualisation" ]; then \
  		while IFS= read -r file; do \
            if [ -e "pip/504/$$file" ]; then \
                mkdir -p "fs/dependencies/$$(dirname "$$file")"; \
                cp "pip/504/$$file" "fs/dependencies/$$(dirname "$$file")"; \
            else \
                echo "File pip/504/$$file does not exist"; \
            fi \
        done < "pip/504.txt"; \
        \
        docker run --privileged -v $${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libstdc++.so.6 /build/fs/lib/; \
        docker run --privileged -v $${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libgcc_s.so.1 /build/fs/lib/; \
	else \
	  	echo "Wrong benchmark name."; \
	  	exit 1; \
	fi

	cd runtime/filesystem/sebs; ./create.sh


boottime_setup:
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
	cp module/libsysdb.so Benchmarks/IPC/wallet/
	cp module/libpal.so Benchmarks/IPC/wallet/

IPC_ITERATIONS?=5
IPC_SIZE?=64
ssh_ipc:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "cd Benchmarks/IPC/wallet/; python3 run.py ${IPC_SIZE} ${IPC_ITERATIONS}"

ipc:
	cd Benchmarks/IPC/wallet/; ./run.sh

shutdown:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.${USERADDR}.10 "shutdown now"

boottime:
	cd Benchmarks/Boottime/wallet/; ITER=${BOOTTIME_ITERATION} ./run.sh
	cd Benchmarks/Boottime/wallet/; python parse_boottime.py
