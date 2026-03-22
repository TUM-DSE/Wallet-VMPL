#!/usr/bin/env bash
shopt -s extglob
set -x
set -e

cd /mount/$1
make clean
make olddefconfig
scripts/config --disable SYSTEM_TRUSTED_KEYRING
scripts/config --disable SYSTEM_TRUSTED_KEYS
scripts/config --disable SYSTEM_REVOCATION_KEYS
scripts/config --disable SYSTEM_TRUSTED_KEYRING
scripts/config --disable SYSTEM_BLACKLIST_KEYRING
scripts/config --disable SYSTEM_EXTRA_CERTIFICATE
scripts/config --disable SECONDARY_TRUSTED_KEYRING
scripts/config --disable DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT
make olddefconfig

mkdir -p /mount/build/$1/

# Clean old debs before building so globs match exactly one file
cd /mount/$1/../
rm -f linux-headers-6.5.0*.deb linux-image-6.5.0*.deb linux-libc-dev_6.5.0*.deb

cd /mount/$1
make bindeb-pkg -j $(nproc) LOCALVERSION=-svsm

cd /mount/$1/../
rm -f /mount/build/$1/*
cp linux-headers-6.5.0*.deb /mount/build/$1/linux-headers-6.5.0-svsm.deb
cp linux-image-!(*dbg*).deb /mount/build/$1/linux-image-6.5.0-svsm.deb
cp linux-libc-dev_6.5.0*.deb /mount/build/$1/linux-libc-dev_6.5.0-svsm.deb

# Clean up debs from project root
rm -f linux-headers-6.5.0*.deb linux-image-6.5.0*.deb linux-libc-dev_6.5.0*.deb
