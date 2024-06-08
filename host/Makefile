
KERNELDIR := $(shell nix build --print-out-paths "/etc/nixos/#nixosConfigurations.ryan.config.boot.kernelPackages.kernel.dev")

.PHONY: kvm unload_kvm load_kvm

kvm: 
	make -C ${KERNELDIR}/lib/modules/*/build M=${CURDIR}/kvm/ -j64

unload_kvm: 
	sudo rmmod kvm_amd
	sudo rmmod kvm

load_kvm:
	sudo insmod kvm/kvm.ko
	sudo insmod kvm/kvm-amd.ko