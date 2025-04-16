#!/usr/bin/env bash

cd ../
mkdir -p log/run

benchmarks=(
    "110.dynamic-html"
    #"120.uploader"
    "210.thumbnailer"
    "220.video-processing"
    "311.compression"
    #"411.image-recognition"
    "501.graph-pagerank"
    "502.graph-mst"
    "503.graph-bfs"
    "504.dna-visualisation"
)

delete() {
    sudo rm -rf "Benchmarks/SeBS/$1"
}

run() {
    echo "Starting VM for $1"
    if [ "${4}" == "breakdown" ]; then
        sudo bpftrace boot_time_eval.bt &> "log/run/$3-$1-$2" &
        PIDT=$!
    fi

    MEM=128 make run &> "log/run/$3-$1" &
    PID=$!

    if [ "${2}" == "prealloc" ]; then
        sleep 500
    else
        sleep 50
    fi

    echo "Starting Benchmark $1 - $3"

    make run_benchmark_sebs_cvm name="$1" WARM_COLD="${3}" &> "log/run/$3-$1-bench"

    kill ${PID}
    if [ "${4}" == "breakdown" ]; then
        kill ${PIDT}
    fi
    sleep 10
}

build_monitor() {
    if [ "${1}" == "prealloc" ]; then
        LOG_LEVEL="no_print" SVSM_DEBUG="" FEATURE="boottime prealloc" make build_svsm &> log/svsm_prealloc
    else
        LOG_LEVEL="no_print" SVSM_DEBUG="" FEATURE="boottime " make build_svsm &> log/svsm
    fi
}

copy_to_target() {
    if [ ! -z ${2} ]; then
        rm -rf "./${2}/$1"
        cp -r "Benchmarks/SeBS/$1" "./${2}/$1"
    fi
}

build_monitor $1

for b in ${benchmarks[@]}; do
    date
    delete $b
    run $b $1 $3 $4
    copy_to_target $b $2
done

echo "Done"
