#!/bin/bash
set -eux

# (cd module; make -C libwallet/ clean; make libwallet/libwallet.a NODEBUG=1; make vmpl.ko; insmod vmpl.ko; rm -r python/build)
(cd module; insmod vmpl.ko)
# apt install -y build-essential python3-dev python3-venv python3-pip docker.io jq
cd Benchmarks/SeBS/
# ./install.py --no-aws --azure --no-gcp --no-openwhisk --local
source python-venv/bin/activate
# pip3 install ../../module/python
# tools/build_docker_images.py --deployment 'wallet' --language 'python' --language-version '3.11'
./sebs.py storage start minio --port '9011' --output-json 'out_storage.json'
rm -r cache/

jq ".deployment.wallet.storage = input | .experiments.\"perf-cost\".benchmark = \"$1\"" 'config/config_template.json' 'out_storage.json' > 'config/config.json'

./sebs.py experiment invoke perf-cost --config 'config/config.json' --output-dir $1 --output-file 'run.log'
./sebs.py experiment process perf-cost --config 'config/config.json' --output-dir $1 --output-file 'process.log'
