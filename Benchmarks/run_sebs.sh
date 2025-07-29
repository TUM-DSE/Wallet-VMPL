#!/usr/bin/env bash

PREALLOC="${1:-prealloc}"
SUB_RESULT_PATH="${2:-Benchmarks/SeBS_analysis/results/default}"
SEBS_TARGET="${3:-wallet}"
COW_CONFIG="${4:-cow}"
BENCH_FEATURE="${5:-breakdown}"
MEASURE="${6:-no_measure}"
EXTERNAL="${7:-not_external}"
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

setup_libos() {

    name=$1
    if [ "${name}" == "110.dynamic-html" ]; then
        cp module/libpal-html.so module/libpal.so;
        cp module/libsysdb-html.so module/libsysdb.so;
    elif [ "${name}" == "120.uploader" ]; then
        cp module/libpal-none.so module/libpal.so;
        cp module/libsysdb-none.so module/libsysdb.so;
    elif [ "${name}" == "210.thumbnailer" ]; then
        cp module/libpal-thumbnailer.so module/libpal.so;
        cp module/libsysdb-thumbnailer.so module/libsysdb.so;
    elif [ "${name}" == "220.video-processing" ]; then
        cp module/libpal-video.so module/libpal.so;
        cp module/libsysdb-video.so module/libsysdb.so;
    elif [ "${name}" == "311.compression" ]; then
        cp module/libpal-none.so module/libpal.so;
        cp module/libsysdb-none.so module/libsysdb.so;
    elif [ "${name}" == "411.image-recognition" ]; then
        cp module/libpal-image-recognition.so module/libpal.so;
        cp module/libsysdb-image-recognition.so module/libsysdb.so;
    elif [ "${name}" == "501.graph-pagerank" ] || [ "${name}" == "502.graph-mst" ] || [ "${name}" == "503.graph-bfs" ]; then
        cp module/libpal-igraph.so module/libpal.so;
        cp module/libsysdb-igraph.so module/libsysdb.so;
    elif [ "${name}" == "504.dna-visualisation" ]; then
        cp module/libpal-dna.so module/libpal.so;
        cp module/libsysdb-dna.so module/libsysdb.so;
    else
        sleep 1;
        echo "Benchmark ${name} not found";
        exit 1;
    fi
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

    echo "Collecting time trace"
    echo "Storing in: ${RESULT_PATH}/time-trace-${BENCH}"
    sudo bpftrace time.bt &> "${RESULT_PATH}/time-trace-${BENCH}" &
    PIDT=$!

    MEM=128 make run &> "${RESULT_PATH}/${SEBS_TARGET}-${BENCH}" &
    PID=$!

    if [ "${PREALLOC}" == "prealloc" ]; then
        sleep 280
    else
        sleep 50
    fi

    echo "Starting Benchmark ${BENCH} - ${PREALLOC} - ${COW_CONFIG}"

    if [ "${EXTERNAL}" == "external" ]; then
        setup_libos $BENCH
        WALLET_ADDR="192.168.27.10" ./Benchmarks/sebs_script_extern.sh ${BENCH} "wallet_remote" &> "${RESULT_PATH}/${SEBS_TARGET}-${BENCH}-bench"
        STATE=$?
    else
        timeout 1800s make run_benchmark_sebs name="${BENCH}" WARM_COLD="${SEBS_TARGET}" &> "${RESULT_PATH}/${SEBS_TARGET}-${BENCH}-bench"
        STATE=$?
    fi

    kill ${PID}
    if [ "${BENCH_FEATURE}" == "breakdown" ] || [ "${BENCH_FEATURE}" == "stat" ]; then
        kill ${PIDT}
    fi
    kill ${PIDT}
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
