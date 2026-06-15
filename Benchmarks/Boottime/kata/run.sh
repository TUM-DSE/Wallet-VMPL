#!/usr/bin/env sh

ITERATIONS=10

rm -rf result/
mkdir -p result/

for i in $(seq 0 $(expr ${ITERATIONS} - 1))
do
    sudo bpftrace ./boot_time_eval.bt > result/res-${i}.txt &
    PID=$!
    sleep 5
    start_time=$(date +%s%N)
    end_time=$(docker run --runtime kata-qemu-slick ubuntu:24.04 date +%s%N)
    sudo journalctl -n50 -t kata > result/log-${i}.txt
    sudo kill ${PID}
    sleep 5
    echo "Start: $start_time" > result/se-${i}.txt
    echo "End: $end_time" >> result/se-${i}.txt
done

python3 parse.py $ITERATIONS
