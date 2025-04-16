#!/bin/bash
set -eux
TARGET="${2:-wallet}"

cd Benchmarks/SeBS/
rm -r cache/ || true

./install.py --no-aws --azure --no-gcp --no-openwhisk --local

source python-venv/bin/activate

tools/build_docker_images.py --deployment "${TARGET}" --language 'python' --language-version '3.11'
./sebs.py storage start minio --port '9011' --output-json 'out_storage.json'

jq ".deployment.name = \"${TARGET}\" | .deployment.${TARGET}.storage = input | .experiments.\"perf-cost\".benchmark = \"$1\"" 'config/config_template.json' 'out_storage.json' > 'config/config.json'

./sebs.py experiment invoke perf-cost --config 'config/config.json' --output-dir $1 --output-file 'run.log'
./sebs.py experiment process perf-cost --config 'config/config.json' --output-dir $1 --output-file 'process.log'

./sebs.py storage stop 'out_storage.json'
