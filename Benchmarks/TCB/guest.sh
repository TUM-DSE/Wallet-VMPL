#!/usr/bin/env sh

git clone https://github.com/Sabanic-P/linux.git linux-guest
cd linux-guest
git checkout 7902bb420130420b0a9afa7cddc274bd1bce413c
git clean -xfd
cd ..


inotifywait -m -r -e open --format '%w%f' -o guest_kernel.log ${PWD}/linux-guest/ &
PID=$!
sleep 5

docker run -v ${PWD}:/mount -it vmplbuild bash -c "cd /mount/linux-guest; make defconfig; make -j"

kill $PID

cat guest_kernel.log \
    | grep -E "\.c$|\.h$|\.H$|\.s$|\.S$" \
    | grep -v -E "^\.|^certs|^samples|^scripts|^tools|^usr" > guest_kernel.log.prep

cloc --csv --list-file=guest_kernel.log.prep > guest.csv
cat guest.csv
