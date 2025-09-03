#!/usr/bin/env sh
set -x
chains=(
    2
    4
    8
    16
)

WALLET_VM_ADDRESS="192.168.$(expr $(id -u) % 1000).10"
root=../../../

run_vm() {
    sudo qemu-system-x86_64 \
        -enable-kvm \
        -cpu EPYC-v4,host-phys-bits=true  \
        -machine q35 \
        -m 1G \
        -smp 1 \
        -no-reboot \
        -drive file=${root}guest.qcow2,if=none,id=disk0,format=qcow2,snapshot=off \
        -device virtio-scsi-pci,id=scsi0,disable-legacy=on,iommu_platform=on \
        -device scsi-hd,drive=disk0,bootindex=0 \
        -netdev tap,ifname=tap0_${USER},id=net0,script=no,downscript=no -device e1000,netdev=net0 \
        -serial stdio \
        -serial pty \
        -virtfs local,path=${root}module/,mount_tag=mo,security_model=passthrough \
        -virtfs local,path=${root}Benchmarks/,mount_tag=benchmarks,security_model=passthrough \
        -virtfs local,path=${root}gramine-svsm/,mount_tag=gramine,security_model=passthrough &
    VM=$!
}



start_server() {
    port=4443
    addr=$2
    next_addr=$3
    echo $1 $2 $3
    ssh -i ${root}container/key -o StrictHostKeychecking=no root@${WALLET_VM_ADDRESS}\
        "python3 Benchmarks/IPC/extended/server.py ${port} &> /dev/null" &
    sleep 1
}

if [ "$1" == "VM" ]; then
	#VM
	run_vm
	sleep 10
	start_server
	sleep 10
	python3 client.py "http://${WALLET_VM_ADDRESS}:4443" "vm"
	sudo kill $VM
	sleep 5
fi

if [ "$1" == "CVM" ]; then
        #VM
	(cd ${root}/; make build_svsm)
	make -C ${root} run &
        sleep 100
        start_server
        sleep 10
        python3 client.py "http://${WALLET_VM_ADDRESS}:4443" "cvm"
        sudo kill $VM
        sleep 5
fi

if [ "$1" == "kata" ]; then
	#Kata
	docker run --rm --runtime kata-qemu  -p 4443:4443 kataserver bash -c "python3 server.py &> /dev/null" &
	VM=$!
	sleep 5
	python3 client.py "http://localhost:4443" "kata"
	kill $VM
fi


