
BUILD_EXTENSIONS_AS_BUILTIN = ON
PYTHON_VERSION = 3.11.10

python: python-install/bin/python

python-install/bin/python:
	mkdir -p python-build
	mkdir -p python-install
	cd python-build; cmake -DBUILD_EXTENSIONS_AS_BUILTIN=${BUILD_EXTENSIONS_AS_BUILTIN} -DPYTHON_VERSION=${PYTHON_VERSION} -DCMAKE_INSTALL_PREFIX:PATH=../python-install ../portable-python-cmake-buildsystem
	cd python-build;make -j
	cd python-build; make install
	make python_app

test_build:
	sudo rm -r python-build
	sudo rm -r python-install
	mkdir -p python-build

CFLAGS=-I./python-install/include/python3.11/ -Wno-unused-result -Wsign-compare -fno-semantic-interposition -DNDEBUG -g -fwrapv -O3 -Wall
LDFLAGS=-L./python-install/lib -l:libpython3.11.a -lcrypt -ldl -lsqlite3 -lm -lz -lssl -lcrypto -llzma -lgdbm -lexpat -lbz2 -lgdbm_compat -lffi -luuid

libcpuid.so: client/cpuid.c
	gcc -shared -fpic client/cpuid.c -o libcpuid.so

python_embedded: embed/main.c
	gcc ${CFLAGS} embed/main.c -o python_embedded ${LDFLAGS} -L. -l:libcpuid.so

python_app: libcpuid.so python_embedded

python_fs: python python_app
	cd filesystem/python/; ./python_deps.sh
	rm -f python-install/lib/python3.11/config/libpython3.11.a

prepare_python_libs:
	pip install --target=pip/ -r requirements.txt
