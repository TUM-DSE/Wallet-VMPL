cd ../../../;

LOG_LEVEL="no_print" SVSM_DEBUG="" FEATURE="prealloc breakdown" make build_svsm
if [ $? -eq 0 ]; then
	echo "Monitor build successfully"
else
	echo "Monitor build failed"
	exit
fi

MEM=128 make run &> Benchmarks/Attestation/breakdown/vm &
PID=$!

sleep 280

SSH_COMMAND="cd module; make reload;" make ssh_with_command

for i in 1 2 3 4 5 6 7 8 9 10; do
	sudo bpftrace boot_time_eval.bt &> "Benchmarks/Attestation/breakdown/trace_${i}" &
	PIDB=$!
	sleep 5 

	SSH_COMMAND="cd Benchmarks/Attestation/breakdown; python3 run.py" make ssh_with_command
	sleep 1
	kill $PIDB
done;

kill $PID
