#!/usr/bin/env bash

sizes=(64 128 256 512 1024 2048 4096 8192 16384 32768 65546 131072 262144 524288 1048576 2096152)
mkdir -p result/
rm result/*

make -C ../../../ run > run.log &
sleep 400

for i in "${sizes[@]}"
do
    sudo bpftrace com.bt > result/res-${i}.txt &
    PID=$!
    sleep 5
    IPC_SIZE=${i} make -C ../../../ ssh_ipc
    sudo kill ${PID}
    sleep 5
done

make -C ../../../ shutdown
