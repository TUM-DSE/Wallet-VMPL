#!/usr/bin/env bash

if [[ "$1" = "docker" ]]
then
    time1=$(date +%s%N)

    time2=$(gramine-direct /root/gramine-boottime)

    diff=$((time2 - time1))

    seconds=$((diff / 1000000000))
    nanoseconds=$((diff % 1000000000))

    echo "Time difference: $diff nanoseconds"
    echo "Time difference: $seconds seconds and $nanoseconds nanoseconds"

else
    docker run --rm -v $(pwd):/root --security-opt "seccomp=unconfined" gramineproject/gramine:1.7-jammy "bash /root/gramine.sh docker"
fi
