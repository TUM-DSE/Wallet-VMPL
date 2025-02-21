#!/usr/bin/env bash

PYTHONPATH=../../python-install/

cp ${PYTHONPATH}/bin/python fs/python/python


LIBPATH=../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/
LIBOSPATH=../../../gramine-svsm/libos

cp ${LIBPATH}/libc.so.6 fs/lib/
cp ${LIBPATH}/libm.so.6 fs/lib/
cp ${LIBPATH}/ld-linux-x86-64.so.2 fs/lib/
cp ${LIBPATH}/libpthread.so.0 fs/lib/

cp ../../libcpuid.so fs/lib/

if [ ! -f fs/python/stdlib.zip ]; then
    rm -f ${PYTHONPATH}/lib/python3.11/config/libpython3.11.a
    (cd ${PYTHONPATH}/lib/python3.11/; zip -r ../../../filesystem/sebs/fs/python/stdlib.zip *)
fi

rm -r fs_out
FS_IN="sebs/fs/" FS_OUT="sebs/fs_out/" python ../fs.py

rm -rf ${LIBOSPATH}/src/fs/static/files
mkdir -p ${LIBOSPATH}/src/fs/static/files/

cp fs_out/fs.c ${LIBOSPATH}/src/fs/static/
cp -r fs_out/files/ ${LIBOSPATH}/src/fs/static/
cp fs_out/*.h ${LIBOSPATH}/include/
