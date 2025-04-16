#!/bin/bash
set -eux
TARGET="${2:-wallet}"
(cd module; make clean; make -C libwallet/ clean; rm -r python/build || true)

(cd module; make libwallet/libwallet.a NODEBUG=1; make vmpl.ko; insmod vmpl.ko || true)

apt install -y python3-bottle
(cd Benchmarks/SeBS/; pip3 install ../../module/python)
