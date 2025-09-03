#!/usr/bin/env bash

cd ../

make build_svsm
make run &
PID=$!

sleep 30

ssh -i ./container/key -o StrictHostKeychecking=no root@$1 \
	"cd module; make -B vmpl.ko"
ssh -i ./container/key -o StrictHostKeychecking=no root@$1 \
	"cd module; make libwallet/libwallet.a libwallet/libwallet.so"
ssh -i ./container/key -o StrictHostKeychecking=no root@$1 \
	"cd module/python; python3 -m pip install pybind11 pytest fire; python3 setup.py install; touch build_python;"

ssh -i ./container/key -o StrictHostKeychecking=no root@$1 \
	"shutdown now"

sleep 5
sudo kill $PID &> /dev/null

exit 0


