#!/usr/bin/env sh

cd ../../gramine-svsm
rm -rf libos/src/fs/static/files/*
find ${PWD}/pal ${PWD}/libos > ../Benchmarks/TCB/gramine.log

cd ../Benchmarks/TCB/
cat gramine.log \
    | grep -E "\.c$|\.h$|\.H$|\.s$|\.S$" \
    | grep -v -E "^\.|^certs|^samples|^scripts|^tools|^usr"  \
    | grep -vwE "(test|linux-sgx|regression|linux|skeleton)"> gramine.log.prep

cloc --csv --list-file=gramine.log.prep > gramine.csv
cat gramine.csv
