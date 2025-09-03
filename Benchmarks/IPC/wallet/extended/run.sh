#!/usr/bin/env bash

cd ../../../../

make run & &> /dev/null
sleep 300

SSH_COMMAND="(cd module; make clean; make -C libwallet/ clean; rm -rf python/build || true)" \
    make ssh_with_command

SSH_COMMAND="(cd module; make libwallet/libwallet.a NODEBUG=1; make vmpl.ko; insmod vmpl.ko || true)" \
    make ssh_with_command

SSH_COMMAND="(cd Benchmarks/IPC/wallet/extended/; python3 run.py)" \
    make ssh_with_command

make shutdown
