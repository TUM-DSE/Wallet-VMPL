#!/usr/bin/env sh

ITERATIONS=10

rm -rf result/
mkdir -p result/

#docker run --privileged -v ${PWD}/Benchmarks/Boottime/gramine/:/bench/ -v ${PWD}/gramine-svsm/:/gramine -w /gramine -it gramine-build-container

for i in $(seq 0 $(expr ${ITERATIONS} - 1))
do
    start_time=$(date +%s%N)
    times=$(gramine-direct gramine-boottime 2>&1)

    echo "${start_time}" > result/res-${i}.txt
    echo "${times}" >> result/res-${i}.txt

    sleep 1
done

#python3 parse.py $ITERATIONS
