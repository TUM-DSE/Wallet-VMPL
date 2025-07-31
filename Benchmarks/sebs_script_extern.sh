#!/usr/bin/env bash
set -eux
TARGET="${2:-wallet_remote}"

SSH_COMMAND="(cd module; make clean; make -C libwallet/ clean; rm -rf python/build || true)" \
    make ssh_with_command

#docker volume prune -f

SSH_COMMAND="(cd module; make libwallet/libwallet.a NODEBUG=1; make vmpl.ko; insmod vmpl.ko || true)" \
    make ssh_with_command

cd Benchmarks/SeBS/
sudo rm -rf cache/ || true

./install.py --no-aws --azure --no-gcp --no-openwhisk --local
source python-venv/bin/activate
#pip3 install ../../module/python

tools/build_docker_images.py --deployment "${TARGET}" --language 'python' --language-version '3.11'
./sebs.py storage start minio --port '9011' --output-json 'out_storage.json'

jq ".deployment.name = \"${TARGET}\"" 'config/config_template.json' > 'config/config_tmp.json'

jq ".deployment.${TARGET}.storage = input | .experiments.\"perf-cost\".benchmark = \"$1\"" 'config/config_tmp.json' 'out_storage.json' > 'config/config.json'

./sebs.py experiment invoke perf-cost --config 'config/config.json' --output-dir $1 --output-file 'run.log'
./sebs.py experiment process perf-cost --config 'config/config.json' --output-dir $1 --output-file 'process.log'

sudo kill $(pgrep minio)
