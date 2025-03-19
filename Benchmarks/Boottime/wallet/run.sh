#!/usr/bin/env sh

mkdir -p result/
rm result/*

for i in $(seq 0 $(expr ${ITER} - 1))
do
	sudo bpftrace boot_time_eval.bt > result/res-${i}.txt &
	PID=$!
	sleep 5
	make -C ../../../ run > /dev/null &
	if [ "${1}" == "prealloc" ]; then
		sleep 400
	else
		sleep 30
	fi
	make -C ../../../ shutdown
	sudo kill ${PID}
	sleep 5
done
