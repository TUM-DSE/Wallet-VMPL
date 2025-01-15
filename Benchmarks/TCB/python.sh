#!/usr/bin/env sh


cd ../../runtime
find ${PWD}/Python-3.11.10 > ../Benchmarks/TCB/python.log

cd ../Benchmarks/TCB/

cat python.log \
    | grep -E "\.c$|\.h$|\.H$|\.s$|\.S$" \
    | grep -v -E "^\.|^certs|^samples|^scripts|^tools|^usr" > python.log.prep

cloc --csv --list-file=python.log.prep > python.csv
cat python.csv
