#!/bin/bash
shopt -s extglob

cd /mount/$1
make olddefconfig
scripts/config --disable SYSTEM_TRUSTED_KEYS
scripts/config --disable SYSTEM_REVOCATION_KEYS
scripts/config --disable SYSTEM_TRUSTED_KEYRING
scripts/config --disable SYSTEM_BLACKLIST_KEYRING
scripts/config --disable SYSTEM_EXTRA_CERTIFICATE
scripts/config --disable SECONDARY_TRUSTED_KEYRING

mkdir -p /mount/build/$1/
make bindeb-pkg -j $(nproc) LOCALVERSION=-svsm
#KBUILD_OUTPUT=/mount/$1/../build
cd /mount/$1/../
cp linux-headers-6.5.0* /mount/build/$1/linux-headers-6.5.0-svsm.deb
cp linux-image-!(*dbg*).deb /mount/build/$1/linux-image-6.5.0-svsm.deb
cp linux-libc-dev_6.5.0* /mount/build/$1/linux-libc-dev_6.5.0-svsm.deb
