#!/usr/bin/env bash

time1=$(date +%s%N)

time2=$(docker run --runtime kata-qemu ubuntu:24.04 date +%s%N)

diff=$((time2 - time1))

seconds=$((diff / 1000000000))
nanoseconds=$((diff % 1000000000))

echo "Time difference: $diff nanoseconds"
echo "Time difference: $seconds seconds and $nanoseconds nanoseconds"
