#!/usr/bin/env bash

if [[ "$1" = "docker" ]]
then
    cd /root

    gramine-manifest -Dpwd=$(pwd) /root/gramine-communication_cost.manifest.template /root/gramine-communication_cost.manifest

    sizes=(64 128 256 512 1024 2048 4096 8192 16384 32768 65536 131072 262144 524288 1048576 2097152)
    for i in "${sizes[@]}"
    do
        echo "microseconds" >> result_gramine/res-$i.txt
        for j in {1..20}
        do
            exec 3< <(gramine-direct /root/gramine-communication_cost receive $i)
            sleep 1
            time1=$(gramine-direct /root/gramine-communication_cost 127.0.0.1 $i)
            time2=$(cat <&3)

            diff=$((time2 - time1))
            echo "diff: $diff"
            echo "$diff" >> result_gramine/res-$i.txt
        done
    done
else
    mkdir -p result_gramine/
    rm -f result_gramine/*

    make gramine

    docker run --rm -v $(pwd):/root --security-opt "seccomp=unconfined" gramineproject/gramine:1.7-jammy "bash /root/gramine.sh docker"
fi
