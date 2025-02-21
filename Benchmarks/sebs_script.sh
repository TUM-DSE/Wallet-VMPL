#!/bin/bash
set -eux

(cd module; make clean; make -C libwallet/ clean; rm -r python/build || true)
docker volume prune -f

(cd module; make libwallet/libwallet.a NODEBUG=1; make vmpl.ko; insmod vmpl.ko || true)

cd Benchmarks/SeBS/
rm -r cache/ || true

./install.py --no-aws --azure --no-gcp --no-openwhisk --local
source python-venv/bin/activate
pip3 install ../../module/python

tools/build_docker_images.py --deployment 'wallet' --language 'python' --language-version '3.11'
./sebs.py storage start minio --port '9011' --output-json 'out_storage.json'

jq ".deployment.wallet.storage = input | .experiments.\"perf-cost\".benchmark = \"$1\"" 'config/config_template.json' 'out_storage.json' > 'config/config.json'

./sebs.py experiment invoke perf-cost --config 'config/config.json' --output-dir $1 --output-file 'run.log'
./sebs.py experiment process perf-cost --config 'config/config.json' --output-dir $1 --output-file 'process.log'
