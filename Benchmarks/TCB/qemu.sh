#!/usr/bin/env sh

mkdir -p qemu
wget https://github.com/Sabanic-P/qemu/releases/download/v8.2.0-igvm/qemu8.2.0.tar.gz
tar -zxf qemu8.2.0.tar.gz -C qemu/

find qemu/ > qemu.log
cat qemu.log \
    | grep -E "\.c$|\.h$|\.H$|\.s$|\.S$" \
    | grep -v -E "^\.|^certs|^samples|^scripts|^tools|^usr" > qemu.log.prep

cloc --csv --list-file=qemu.log.prep > qemu.csv
cat qemu.csv
