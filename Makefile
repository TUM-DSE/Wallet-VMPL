ROOT_PATH?=$(shell pwd)
MODULE_PATH?=${ROOT_PATH}/module/
KERNEL_PATH?=${ROOT_PATH}/linux/
KERNEL_PATCH?=${ROOT_PATH}/kernel.patch
USER?=$(shell whoami)
GUEST_PATH?=${ROOT_PATH}/tmp/
CORES?=1

SOURCE_IMAGE=tmp
IMAGE_NAME=guest


IMAGE_SIZE=10
UBUNTU_IMAGE=https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
KERNEL_DIRS = kernel/linuxamd/ kernel/linux/ kernel/linux-guest/
CONFIG_FILES = $(addsuffix .config,$(KERNEL_DIRS))
USERADDR = $(shell expr $(shell id -u) - 1000)

.PHONY: build_firmware setup_guest_net del_guest_net kvm unload_kvm load_kvm

#Build OVMF Firmware
build_firmware:
	#git submodule init; git submodule update
	cd edk2/; git submodule init; git submodule update
	cd edk2/; PYTHON3_ENABLE=TRUE  PYTHON_COMMAND=python3 make -j16 -C BaseTools/
	cd edk2/; PYTHON3_ENABLE=TRUE  PYTHON_COMMAND=python3 source ./edksetup.sh; \
	PYTHON3_ENABLE=TRUE PYTHON_COMMAND=python3 build -a X64 -b RELEASE -t GCC5 -D DEBUG_ON_SERIAL_PORT -DTPM2_ENABLE -p OvmfPkg/OvmfPkgX64.dsc
	mkdir -p firmware
	cp edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF_CODE.fd firmware/
	cp edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF_VARS.fd firmware/
	cp edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF.fd firmware/

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
	cd svsm; FW_FILE=../firmware/OVMF.fd make FEATURES=enable-gdb RELEASE=True
node/bin/node:
	cd node; make
	cp node/bin/node module/

clean:
	git submodule foreach --recursive git clean -xfd
	cd node; make clean

submodules:
	git submodule update --init --recursive svsm;
#The coconut edk2 repository currently tries to clone some deleted repo
#git submodule update --init --recursive edk2
	cd svsm/kernel/src/my_crypto/; ./build.sh
	git submodule update --init --recursive gramine-svsm;
	git submodule update --init --recursive Benchmarks/SeBS;

prepare_all: submodules build_svsm guest.qcow2 setup_guest_net 

build_and_run: build_svsm run

## Runs guest.qcow2 with SVSM
## Mounts ./module/ at /root/module 
run:
	sudo qemu-system-x86_64 \
	-enable-kvm \
	-cpu EPYC-v4,host-phys-bits=true  \
	-machine q35,confidential-guest-support=sev0,memory-backend=ram1 \
	-object memory-backend-memfd,id=ram1,size=8G,share=true \
	-object sev-snp-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,igvm-file=svsm/bin/coconut-qemu.igvm \
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
	cd gramine-svsm; make build_external
	cp gramine-svsm/build/pal/src/host/svsm/libpal.so module/
	cp gramine-svsm/build/libos/src/libsysdb.so module/
