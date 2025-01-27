#!/usr/bin/env bash
PYTHONPATH=../../python-install/

DEPS=($(ldd ${PYTHONPATH}/bin/python | gawk '{if ($0~/=>/ && $0 !~/not found/) {split($0, a, " "); {if ($0 !~/libc.so/ ) { if ($0!~/libm.so/) print a[3]}}}}'))

for dep in "${DEPS[@]}"
do
    cp ${dep} fs/lib/
done
