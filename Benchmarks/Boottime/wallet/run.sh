#!/usr/bin/env sh

mkdir -p result/
rm result/*

for i in $(seq 0 $(expr ${ITER} - 1))
do
	sudo bpftrace boot_time_eval.bt > result/res-${i}.txt &
	PID=$!
	sleep 5
	make -C ../../../ run > /dev/null &
	sleep 20
	make -C ../../../ shutdown
	sudo kill ${PID}
	sleep 5
done
