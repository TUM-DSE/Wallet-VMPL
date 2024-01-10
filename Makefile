ROOT_PATH?=$(shell pwd)
MODULE_PATH?=${ROOT_PATH}/module/
KERNEL_PATH?=${ROOT_PATH}/linux/
KERNEL_PATCH?=${ROOT_PATH}/kernel.patch
USER=$(shell whoami)
GUEST_PATH?=${ROOT_PATH}/tmp/

IMAGE_SIZE=10
UBUNTU_IMAGE=https://cloud-images.ubuntu.com/jammy/20231207/jammy-server-cloudimg-amd64.img
KERNEL_DIRS = kernel/linuxamd/ kernel/linux/ kernel/linux-guest/
CONFIG_FILES = $(addsuffix .config,$(KERNEL_DIRS))


.PHONY: build_firmware setup_guest_net del_guest_net

#Build OVMF Firmware
build_firmware:
	git submodule init; git submodule update
	cd edk2/; git submodule init; git submodule update
	cd edk2/; PYTHON3_ENABLE=TRUE  PYTHON_COMMAND=python3 make -j16 -C BaseTools/
	cd edk2/; PYTHON3_ENABLE=TRUE  PYTHON_COMMAND=python3 source ./edksetup.sh; PYTHON3_ENABLE=TRUE  PYTHON_COMMAND=python3 build -a X64 -b DEBUG -t GCC5 -D DEBUG_ON_SERIAL_PORT -D DEBUG_VERBOSE -p OvmfPkg/OvmfPkgX64.dsc
	mkdir -p firmware
	cp edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF_CODE.fd firmware/
	cp edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF_VARS.fd firmware/

firmware/OVMF_CODE.fd: build_firmware
firmware/OVMF_VARS.fd: build_firmware

#Get guest image
tmp.qcow2:
	wget ${UBUNTU_IMAGE} -O $@

config: tmp.qcow2
	virt-copy-out -a tmp.qcow2 /boot/config-5.15.0-89-generic .
	mv config-5.15.0-89-generic config

guest.qcow2: tmp.qcow2 scripts/build_image.sh
	bash ./scripts/build_image.sh tmp guest linux ${IMAGE_SIZE}

linux/.config:
	cp config linux/.config

#Build container to build svsm kernel image
.buildcontainer: container/Dockerfile container/build.sh container/user.sh
	cd container; docker build -f Dockerfile -t vmplbuild .
	touch .buildcontainer

build/kernel/linux/linux:
	docker run -v ${shell pwd}:/mount -it vmplbuild bash -c "./user.sh $(shell id -g) $(shell id -u) linux"

setup_guest_net: #131.159.254.1
	sudo ip tuntap add tap0_${USER} mode tap
	sudo ip addr add 192.168.120.1/24 dev tap0_${USER}
	sudo ip link set up dev tap0_${USER}
	sudo iptables -t nat -A POSTROUTING -o enp2s0f0np0 -j MASQUERADE

del_guest_net:
	sudo ip link delete tap0_${USER}
	sudo iptables -t nat -D POSTROUTING -o enp2s0f0np0 -j MASQUERADE
	echo ""

prepare: .toolchain

.toolchain: #rustup override set nightly 
	rustup toolchain install nightly
	rustup target add x86_64-unknown-none
	touch .toolchain

svsm/svsm.bin: build_svsm

build_svsm:
	cd svsm; make FEATURES=enable-gdb

clean:
	git submodule foreach --recursive git clean -xfd

submodules:
	git submodule update --init --recursive

prepare_all: submodules prepare build_svsm guest.qcow2 setup_guest_net

## Runs guest.qcow2 with SVSM
## Mounts ./module/ at /root/module 
run_svsm:
	qemu-system-x86_64 \
	-enable-kvm \
	-cpu EPYC-v4,host-phys-bits=true  \
	-machine q35,confidential-guest-support=sev0,memory-backend=ram1,kvm-type=protected \
	-object memory-backend-memfd-private,id=ram1,size=8G,share=true \
	-object sev-snp-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,svsm=on \
	-smp 8 \
	-no-reboot \
	-drive if=pflash,format=raw,unit=0,file=firmware/OVMF_CODE.fd,readonly=on \
	-drive if=pflash,format=raw,unit=1,file=firmware/OVMF_VARS.fd,snapshot=on \
	-drive if=pflash,format=raw,unit=2,file=svsm/svsm.bin,readonly=on \
	-drive file=guest.qcow2,if=none,id=disk0,format=qcow2,snapshot=off \
	-device virtio-scsi-pci,id=scsi0,disable-legacy=on,iommu_platform=on \
	-device scsi-hd,drive=disk0,bootindex=0 \
	-netdev tap,ifname=tap0_${USER},id=net0,script=no,downscript=no -device e1000,netdev=net0 \
	-serial stdio \
	-serial pty \
	-virtfs local,path=module/,mount_tag=mo,security_model=passthrough


#### Does not work
run_svsm2:
	qemu-system-x86_64 \
	-enable-kvm \
	-cpu EPYC-v4,host-phys-bits=true  \
	-machine q35,confidential-guest-support=sev0,memory-backend=ram1,kvm-type=protected \
	-object memory-backend-memfd-private,id=ram1,size=8G,share=true \
	-object sev-snp-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,svsm=on \
	-smp 8 \
	-kernel linux/arch/x86/boot/bzImage \
	-append "root=/dev/vdb console=hvc0 nokaslr" \
	-virtfs local,path=${ROOT_PATH},security_model=none,mount_tag=home \
	-virtfs local,path=${ROOT_PATH}/guest/,security_model=none,mount_tag=linux \
	-no-reboot \
	-drive if=pflash,format=raw,unit=0,file=firmware/OVMF_CODE.fd,readonly=on \
	-drive if=pflash,format=raw,unit=1,file=firmware/OVMF_VARS.fd,snapshot=on \
	-drive if=pflash,format=raw,unit=2,file=svsm/svsm.bin,readonly=on \
	-drive file=guest.qcow2,if=none,id=disk0,format=qcow2,snapshot=off \
	-device virtio-scsi-pci,id=scsi0,disable-legacy=on,iommu_platform=on \
	-device scsi-hd,drive=disk0 \
	-netdev tap,ifname=tap0_${USER},id=net0,script=no,downscript=no -device e1000,netdev=net0 \
	-serial stdio \
	-serial pty \
	-virtfs local,path=module/,mount_tag=mo,security_model=passthrough


ssh:
	ssh -i ./container/key -o StrictHostKeychecking=no root@192.168.120.10


#module/test.ko: module/test.ko 

###
kernel_build:
	cd linux; git apply ../kernel.patch | true
	cp .config linux/.config
	nix-shell '<nixpkgs>' -A linux.dev --run "\
	cd linux;\
        make olddefconfig; \
	make -j$(shell nproc); "

module_build:
	nix-shell '<nixpkgs>' -A linux.dev --run "cd module;\
        make -C ../linux/ M=$(shell pwd)/module"

image_build:
	nix build --out-link ${GUEST_PATH} --builders '' .#vmplguest-image
	install -D -m600 ${GUEST_PATH}/nixos.qcow2 guest.qcow2
###