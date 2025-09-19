#!/usr/bin/env bash
for i in $(seq 1 5); do
	cd ../CVM_eval/benchmarks/boottime
	sudo bpftrace boot_time_eval.bt > /tmp/vm_trace &
	PID=$!

	cd ../../../Boottime

	python vm.py vm >> vm.txt
	sudo kill $PID
done

python vm.py vm_parse

rm vm.txt
reset
