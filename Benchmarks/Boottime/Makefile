

.PHONY: kata_prepare kata kata_reset gramine native vm cvm

kata_prepare:
	sudo cp -n /etc/kata-containers/configuration-qemu.toml /tmp/configuration-qemu.toml.bak
	sudo rm /etc/kata-containers/configuration-qemu.toml 
	sudo cp kata/configuration-qemu.toml /etc/kata-containers/configuration-qemu.toml

kata_reset:
	sudo cp /tmp/configuration-qemu.toml.bak /etc/kata-containers/configuration-qemu.toml

kata:
	make kata_prepare
	cd kata; ./run.sh
	make kata_reset

gramine:
	cd ../../gramine-svsm/; git apply ../patches/gramine_boot.patch
	cd ../../; make gramine
	docker run --privileged -v ${PWD}/gramine/:/bench/ -v ${PWD}/../../gramine-svsm/:/gramine -w /bench -it gramine-build-container ./run.sh
	cd ../../gramine-svsm/; git apply -R ../patches/gramine_boot.patch
	cd ../../; make gramine
	cd gramine/; python3 parse.py 10

native:
	cd native; ./run.sh
	cd native; python parse.py

vm:
	./vm.sh

cvm:
	./cvm.sh
