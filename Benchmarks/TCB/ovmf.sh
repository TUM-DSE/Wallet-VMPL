#!/usr/bin/env sh

(cd ../../; make clear_firmware_build)
inotifywait -m -r -e open --format '%w%f' -o firmware.log ${PWD}/../../edk2/ &
PID=$!
sleep 5
(cd ../../; make build_firmware)
kill $PID
cat firmware.log \
    | grep -E "\.c$|\.h$|\.H$|\.s$|\.S$" \
    | grep -v -E "^\.|^certs|^Build|^samples|^scripts|^tools|^usr" > firmware.log.prep

cloc --csv --list-file=firmware.log.prep > ovmf.csv
cat ovmf.csv
