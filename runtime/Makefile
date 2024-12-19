
BUILD_EXTENSIONS_AS_BUILTIN = ON
PYTHON_VERSION = "3.11.10"

python:
	mkdir -p python-build
	mkdir -p python-install
	apt update
	apt install cmake libffi-dev libssl-dev libgdbm-dev uuid-dev libsqlite3-dev liblzma-dev libbz2-dev libz-dev libgdbm-dev libgdbm-compat-dev -y
	cd python-build; cmake -DBUILD_EXTENSIONS_AS_BUILTIN=${BUILD_EXTENSIONS_AS_BUILTIN} -DPYTHON_VERSION=${PYTHON_VERSION} -DCMAKE_INSTALL_PREFIX:PATH=../python-install ../portable-python-cmake-buildsystem
	cd python-build;make -j
	cd python-build; make install
	make python_app


CFLAGS=-I./python-install/include/python3.11/ -Wno-unused-result -Wsign-compare -fno-semantic-interposition -DNDEBUG -g -fwrapv -O3 -Wall
LDFLAGS=-L./python-install/lib -l:libpython3.11.a -lcrypt -ldl -lsqlite3 -lm -lz -lssl -lcrypto -llzma -lgdbm -lexpat -lbz2 -lgdbm_compat -lffi -luuid


python_app:
	gcc -shared -fpic client/cpuid.c -o libcpuid.so
	gcc ${CFLAGS} embed/main.c -o main ${LDFLAGS} -L. -l:libcpuid.so
