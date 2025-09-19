#!/usr/bin/env bash
for i in $(seq 1 5); do
        cd ../CVM_eval/benchmarks/boottime
        sudo bpftrace boot_time_eval.bt > /tmp/vm_trace &
        PID=$!

        cd ../../../Boottime

        python vm.py cvm >> cvm.txt
        sudo kill $PID
done

python vm.py cvm_parse

rm cvm.txt
reset
