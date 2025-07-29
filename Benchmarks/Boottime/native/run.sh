#!/usr/bin/env bash

ITERATIONS=10
rm -rf result

for i in $(seq 0 $(expr ${ITERATIONS} - 1))
do
	time1=$(date +%s%N)
	time2=$(date +%s%N)
	diff=$((time2 - time1))
	ms=$(echo $diff | awk '{printf "%.9f\n", $1 / 1000000}')
	echo $ms >> result	
done
