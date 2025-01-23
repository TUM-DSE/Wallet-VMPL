#!/usr/bin/env bash

sizes=(64 128 256 512 1024 2048 4096 8192 16384 32768 65536 131072 262144 524288 1048576 2097152)

mkdir -p result/
rm result/*


for i in "${sizes[@]}"
do
    sudo bpftrace com.bt > result/res-${i}.txt &
    PID=$!
    sleep 5
    make -C ../../../ run > /dev/null &
    sleep 30
    IPC_SIZE=${i} make -C ../../../ ssh_ipc
    make -C ../../../ shutdown
    sudo kill ${PID}
    sleep 5
done
