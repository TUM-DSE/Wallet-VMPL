#!/usr/bin/env bash

LIBPATH=../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/
LIBOSPATH=../../../gramine-svsm/libos

cp ${LIBPATH}/libc.so.6 fs/lib/
cp ${LIBPATH}/ld-linux-x86-64.so.2 fs/lib/

FS_IN="simple/fs/" FS_OUT="simple/fs_out/" python ../fs.py

mkdir -p ${LIBOSPATH}/src/fs/static/files/

cp fs_out/fs.c ${LIBOSPATH}/src/fs/static/
cp -r fs_out/files/ ${LIBOSPATH}/src/fs/static/
cp fs_out/*.h ${LIBOSPATH}/include/
