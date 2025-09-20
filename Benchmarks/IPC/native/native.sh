#!/usr/bin/env bash

sizes=(64 128 256 512 1024 2048 4096 8192 16384 32768 65536 131072 262144 524288 1048576 2097152)

mkdir -p result_native/
rm result_native/*

make native

for comm in pipe
do
    echo $comm

    for i in "${sizes[@]}"
    do
        echo "microseconds" >> result_native/res-$comm-$i.txt
        for j in {1..20}
        do
            ./native $comm $i >> result_native/res-$comm-$i.txt
        done
    done
done
