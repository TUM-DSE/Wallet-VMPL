#!/usr/bin/env bash

set -eux
TARGET="${1:-wallet}"

BENCHMARKS=(
    '110.dynamic-html'
    #'120.uploader'
    '210.thumbnailer'
    #'220.video-processing'
    '311.compression'
    '411.image-recognition'
    '501.graph-pagerank'
    '502.graph-mst'
    '503.graph-bfs'
    '504.dna-visualisation'
)

#docker volume prune -f
cd CVM_eval/benchmarks/sebs/SeBS/
sudo rm -rf cache/

sudo rm -rf python-venv/
./install.py --no-aws --azure --no-gcp --no-openwhisk --local
source python-venv/bin/activate

if [ "$TARGET" == "cvm" ] || [ "$TARGET" == "vm" ]; then
    pip install psutil invoke lxml
fi

if [ "$TARGET" == "gramine" ]; then
    PYTHON_VERSION="3.10"
else
    PYTHON_VERSION="3.11"
fi

tools/build_docker_images.py --deployment "${TARGET}" --language 'python' --language-version '3.10'
./sebs.py storage start minio --port '9011' --output-json 'out_storage.json'

jq ".deployment.name = \"${TARGET}\"" 'config/config_template.json' > 'config/config_target.json'
jq ".experiments.runtime.version = \"${PYTHON_VERSION}\"" 'config/config_target.json' > 'config/config_tmp.json'
for i in "${BENCHMARKS[@]}"
do
    echo "BENCHMARK: $i"
    jq ".deployment.${TARGET}.storage = input | .experiments.\"perf-cost\".benchmark = \"$i\"" \
        'config/config_tmp.json' \
        'out_storage.json' > 'config/config.json'

    ./sebs.py experiment invoke perf-cost --config 'config/config.json' --output-dir "$1-$i" --output-file 'run.log'
    ./sebs.py experiment process perf-cost --config 'config/config.json' --output-dir "$1-$i" --output-file 'process.log' #
    echo "BENCHMARK DONE: $i"
done

sudo kill $(pgrep minio)
