#!/usr/bin/env bash

cd ../
mkdir -p log/run

benchmarks=(
    "110.dynamic-html"
    "120.uploader"
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
    #cp -r "Benchmarks/SeBS/$1" Benchmarks/SeBS_new_res/
    sudo rm -rf "Benchmarks/SeBS/$1"
}

run() {
    echo "Starting VM for $1"
    MEM=128 make run &> "log/run/$1" &
    PID=$!
    sleep 500

    echo "Starting Benchmark $1"

    make run_benchmark_sebs name="$1" &> "log/run/$1-bench"

    kill ${PID}
    sleep 10
}

for b in ${benchmarks[@]}; do
    delete $b
    run $b
done

echo "Done"
