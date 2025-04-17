#!/usr/bin/env bash

PREALLOC="${1:-prealloc}"
SUB_RESULT_PATH="${2:-Benchmarks/SeBS_analysis/results/default}"
SEBS_TARGET="${3:-wallet}"
COW_CONFIG="${4:-cow}"
BENCH_FEATURE="${5:-breakdown}"
MEASURE="${6:-no_measure}"
RESULT_PATH="${SUB_RESULT_PATH}/${SEBS_TARGET}_${COW_CONFIG}_${PREALLOC}"

printf "\nConfiguration:\n"
echo "Prealloc config: ${PREALLOC}"
echo "Result Path: ${RESULT_PATH}"
echo "SeBS target: ${SEBS_TARGET}"
echo "CoW config: ${COW_CONFIG}"
echo "Benchmark feature: ${BENCH_FEATURE}"
printf "\n\n"

cd ../

# Creating folder for logs external to SeBS
mkdir -p log/run

mkdir -p $RESULT_PATH


benchmarks=(
    "110.dynamic-html"
    #"120.uploader"
    "210.thumbnailer"
    #"220.video-processing"
    "311.compression"
    "411.image-recognition"
    "501.graph-pagerank"
    "502.graph-mst"
    "503.graph-bfs"
    "504.dna-visualisation"
)

delete() {
    sudo rm -rf "Benchmarks/SeBS/*-$1"
    sudo rm -rf "Benchmarks/SeBS/$1"
}


run() {

    if [ ! -f "running" ]; then
        echo "Stopping"
        exit
    fi

    BENCH=$1
    echo "Starting VM for ${BENCH}"
    if [ "${BENCH_FEATURE}" == "breakdown" ]; then
        TRACE_PATH="${RESULT_PATH}/${SEBS_TARGET}-${BENCH}-${PREALLOC}-${COW_CONFIG}"
        echo "Storing trace in ${TRACE_PATH}"
        sudo bpftrace boot_time_eval.bt &> "${TRACE_PATH}" &
        PIDT=$!
        sleep 1
    fi
    if [ "${BENCH_FEATURE}" == "stat" ]; then
        echo "Preparing trace collection"
        echo "Storing trace in ${RESULT_PATH}/trace-${BENCH}"
        #mkdir -p "Benchmarks/SeBS_analysis/results/wallet_traces_$2"
        sudo bpftrace scripts/kvmexit.bt &> "${RESULT_PATH}/trace-${BENCH}" &
        PIDT=$!
        sleep 1
    fi


    MEM=128 make run &> "${RESULT_PATH}/${SEBS_TARGET}-${BENCH}" &
    PID=$!

    if [ "${PREALLOC}" == "prealloc" ]; then
        sleep 280
    else
        sleep 50
    fi

    echo "Starting Benchmark ${BENCH} - ${PREALLOC} - ${COW_CONFIG}"

    timeout 1800s make run_benchmark_sebs name="${BENCH}" WARM_COLD="${SEBS_TARGET}" &> "${RESULT_PATH}/${SEBS_TARGET}-${BENCH}-bench"
    STATE=$?

    kill ${PID}
    if [ "${BENCH_FEATURE}" == "breakdown" ] || [ "${BENCH_FEATURE}" == "stat" ]; then
        kill ${PIDT}
    fi

    sleep 10

    if [ $STATE -eq 124 ]; then
        echo "Benchmark ${BENCH} failed -- retrying"
        run $BENCH
    fi
}

build_monitor() {
    if [ "${COW_CONFIG}" == "no_cow" ]; then
        COW_FLAG="no_cow"
    else
        COW_FLAG=""
    fi

    if [ "${PREALLOC}" == "prealloc" ]; then
        PREALLOC_FLAG="prealloc"
    else
        PERALLOC_FLAG=""
    fi

    if [ "${MEASURE}" == "measure" ]; then
        BOOTTIME_FLAG=""
    else
        BOOTTIME_FLAG="boottime"
    fi

    if [ "${BENCH_FEATURE}" == "no_feature" ]; then
        ADDITIONAL_FEATURE=""
    else
        ADDITIONAL_FEATURE="${BENCH_FEATURE}"
    fi
    echo "Building Monitor with ${BOOTTIME_FLAG} ${PREALLOC_FLAG} ${COW_FLAG} ${ADDITIONAL_FEATURE}"

    LOG_LEVEL="no_print" SVSM_DEBUG="" FEATURE="${BOOTTIME_FLAG} ${PREALLOC_FLAG} ${COW_FLAG} ${ADDITIONAL_FEATURE}" make build_svsm &> log/svsm
    FAILED=$?

    if [ "${FAILED}" == "0" ]; then
        echo "Monitor build successfully"
    else
        echo "Monitor build failed: ${FAILED}"
        cat log/svsm
        exit
    fi
}

copy_to_target() {
    rm -rf "${RESULT_PATH}/$1"
    cp -r "Benchmarks/SeBS/$1" "${RESULT_PATH}/$1"
}

build_monitor

if [ -f "running" ]; then
    echo "Benchmark is already running!"
    exit -1
fi

touch running

for b in ${benchmarks[@]}; do
    date
    delete $b
    run $b
    copy_to_target $b
done

rm running

echo "Done"
