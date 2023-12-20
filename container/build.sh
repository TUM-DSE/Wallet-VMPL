#!/bin/bash


cd /mount/$1
make olddefconfig
scripts/config --disable SYSTEM_TRUSTED_KEYS
scripts/config --disable SYSTEM_REVOCATION_KEYS
scripts/config --disable SYSTEM_TRUSTED_KEYRING
scripts/config --disable SYSTEM_BLACKLIST_KEYRING
scripts/config --disable SYSTEM_EXTRA_CERTIFICATE
scripts/config --disable SECONDARY_TRUSTED_KEYRING

mkdir -p /mount/build/$1/
make deb-pkg -j $(nproc) LOCALVERSION=-svsm
#KBUILD_OUTPUT=/mount/$1/../build
cd /mount/$1/../
find . -maxdepth 1 -type f -exec mv {} /mount/build/$1 \;
