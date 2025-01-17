#!/usr/bin/env bash
PYTHONPATH=../../python-install/

DEPS=($(ldd ${PYTHONPATH}/bin/python | gawk '{if ($0~/=>/ && $0 !~/not found/) {split($0, a, " "); {if ($0 !~/libc.so/ ) { if ($0!~/libm.so/) print a[3]}}}}'))

mkdir -p fs/lib/

for dep in "${DEPS[@]}"
do
    cp ${dep} fs/lib/
done

cp /lib/x86_64-linux-gnu/libstdc++.so.6 fs/lib/
cp /usr/lib/x86_64-linux-gnu/libgcc_s.so.1 fs/lib/
cp /usr/lib/x86_64-linux-gnu/libpthread.so.0  fs/lib/
