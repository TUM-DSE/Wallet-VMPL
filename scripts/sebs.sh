#!/usr/bin/env bash

cd ../

mkdir log

copy_gramine() {
    cp module/libsysdb.so "module/libsysdb-$1.so"
    cp module/libpal.so "module/libpal-$1.so"
}

build() {
    echo "Building $1"
    make sebs_fs name="$1" > "log/$1"
    make gramine > "log/$1-build"
    echo "Copying $1 -> $2"
    copy_gramine "$2"
}

if [ "$#" -ne 2 ]; then
	build "120.uploader" "none"
	exit
fi

build "110.dynamic-html" "html"
build "120.uploader" "none"
build "210.thumbnailer" "thumbnailer"

build "411.image-recognition" "image-recognition"
build "501.graph-pagerank" "igraph"
build "504.dna-visualisation" "dna"
