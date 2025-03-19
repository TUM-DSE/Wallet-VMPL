#!/usr/bin/env bash
name=$1
sudo rm -rf runtime/filesystem/sebs/fs/lib
# sudo rm -rf runtime/filesystem/sebs/fs/python
mkdir -p runtime/filesystem/sebs/fs/lib
mkdir -p runtime/filesystem/sebs/fs/python
mkdir -p runtime/filesystem/sebs/fs/dependencies
# make python deps and prepare stdlib, libcpuid
docker run --rm --privileged -v ${PWD}/runtime:/build -it gramine-build-container make -C build/ sebs_fs
make -C runtime/ libcpuid.so

# prepare pip
if [ ! -d runtime/filesystem/sebs/pip ]; then
    echo "Fetching pip dependencies"
    pip install --target=runtime/filesystem/sebs/pip/110/ -r Benchmarks/SeBS/benchmarks/100.webapps/110.dynamic-html/python/requirements.txt;
    pip install --target=runtime/filesystem/sebs/pip/210/ -r Benchmarks/SeBS/benchmarks/200.multimedia/210.thumbnailer/python/requirements.txt.3.11;
    pip install --target=runtime/filesystem/sebs/pip/411/ -r Benchmarks/SeBS/benchmarks/400.inference/411.image-recognition/python/requirements.txt.3.11;
    pip install --target=runtime/filesystem/sebs/pip/501/ -r Benchmarks/SeBS/benchmarks/500.scientific/501.graph-pagerank/python/requirements.txt.3.11;
    pip install --target=runtime/filesystem/sebs/pip/504/ -r Benchmarks/SeBS/benchmarks/500.scientific/504.dna-visualisation/python/requirements.txt;
fi

rm -rf runtime/filesystem/sebs/fs/dependencies || true
cd runtime/filesystem/sebs;
echo "Searching for ${name}"
if [ "${name}" == "110.dynamic-html" ]; then
    while IFS= read -r file; do
        if [ -e "pip/110/${file}" ]; then
            mkdir -p "fs/dependencies/$(dirname "${file}")";
            cp "pip/110/${file}" "fs/dependencies/$(dirname "${file}")";
        else
            echo "File pip/110/${file} does not exist";
        fi
    done < "pip_lists/110.txt";

    cp ../../../Benchmarks/SeBS/benchmarks/100.webapps/110.dynamic-html/python/templates/template.html fs/dependencies;
elif [ "${name}" == "120.uploader" ]; then
    mkdir -p fs/dependencies/;
elif [ "${name}" == "210.thumbnailer" ]; then
    while IFS= read -r file; do
        if [ -e "pip/210/${file}" ]; then
            mkdir -p "fs/dependencies/$(dirname  "${file}")";
            cp "pip/210/${file}" "fs/dependencies/$(dirname  "${file}")";
        else
            echo "File pip/210/${file} does not exist";
        fi
    done < "pip_lists/210.txt";
elif [ "${name}" == "220.video-processing" ]; then
    mkdir -p fs/dependencies;
    docker run --rm --privileged -v ${PWD}:/build -it gramine-build-container sh -c "apt update && apt install -y --no-install-recommends ffmpeg &&
    cp /usr/bin/ffmpeg /build/fs/dependencies/";
    cp ../../../Benchmarks/SeBS/benchmarks/200.multimedia/220.video-processing/resources/watermark.png fs/dependencies;
elif [ "${name}" == "311.compression" ]; then
    mkdir -p fs/dependencies/;
    elif [ "${name}" == "411.image-recognition" ]; then
        while IFS= read -r file; do
            if [ -e "pip/411/${file}" ]; then
                mkdir -p "fs/dependencies/$(dirname  "${file}")";
                cp "pip/411/${file}" "fs/dependencies/$(dirname  "${file}")";
            else
                echo "File pip/411/${file} does not exist";
            fi
        done < "pip_lists/411.txt";

    cp ../../../Benchmarks/SeBS/benchmarks/400.inference/411.image-recognition/python/imagenet_class_index.json fs/dependencies;

    cp ../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/libdl.so.2 fs/lib;
    cp ../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/librt.so.1 fs/lib;
    docker run --rm --privileged -v ${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libstdc++.so.6 /build/fs/lib/;
    docker run --rm --privileged -v ${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libgcc_s.so.1 /build/fs/lib/;
elif [ "${name}" == "501.graph-pagerank" ] || [ "${name}" == "502.graph-mst" ] || [ "${name}" == "503.graph-bfs" ]; then
    while IFS= read -r file; do
        if [ -e "pip/501/${file}" ]; then
            mkdir -p "fs/dependencies/$(dirname  "${file}")";
            cp "pip/501/${file}" "fs/dependencies/$(dirname  "${file}")";
        else
            echo "File pip/501/${file} does not exist";
        fi
    done < "pip_lists/501.txt";
   
    cp ../../../gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc/libdl.so.2 fs/lib;
    docker run --rm --privileged -v ${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libstdc++.so.6 /build/fs/lib/;
    docker run --rm --privileged -v ${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libgcc_s.so.1 /build/fs/lib/;
	elif [ "${name}" == "504.dna-visualisation" ]; then
	while IFS= read -r file; do
    if [ -e "pip/504/${file}" ]; then
    mkdir -p "fs/dependencies/$(dirname  "${file}")";
    cp "pip/504/${file}" "fs/dependencies/$(dirname  "${file}")";
    else
    echo "File pip/504/${file} does not exist";
    fi
    done < "pip_lists/504.txt";

    docker run --rm --privileged -v ${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libstdc++.so.6 /build/fs/lib/;
    docker run --rm --privileged -v ${PWD}:/build -it gramine-build-container cp /lib/x86_64-linux-gnu/libgcc_s.so.1 /build/fs/lib/;
else
    echo "Wrong benchmark name.";
    exit 1;
fi
echo "Created Filesystem structure for Benchmark"
echo "Building filesystem"
./create.sh
echo "Done building filesystem"
