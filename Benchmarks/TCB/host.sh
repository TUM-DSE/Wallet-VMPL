#!/usr/bin/env sh

git clone https://github.com/Sabanic-P/linux.git
cd linux
git checkout 29df906740fa864f8ebdcd62c30a20d2a62ec229
git clean -xfd
cd ..


inotifywait -m -r -e open --format '%w%f' -o host_kernel.log ${PWD}/linux/ &
PID=$!
sleep 5

docker run -v ${PWD}:/mount -it vmplbuild bash -c "cd /mount/linux; make defconfig; make -j"

kill $PID
cat host_kernel.log \
    | grep -E "\.c$|\.h$|\.H$|\.s$|\.S$" \
    | grep -v -E "^\.|^certs|^samples|^scripts|^tools|^usr" > host_kernel.log.prep

cloc --csv --list-file=host_kernel.log.prep > host.csv
cat host.csv
