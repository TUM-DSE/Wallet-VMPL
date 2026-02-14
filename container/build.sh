#!/usr/bin/env bash
shopt -s extglob

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
sed -i "s/range 3 300/range 3 86400/" kernel/rcu/Kconfig.debug # increate allowed timeout
scripts/config --set-val RCU_CPU_STALL_TIMEOUT 86400
sed -i "s/range 0 300000/range 3 86400000/" kernel/rcu/Kconfig.debug # increate allowed timeout
scripts/config --set-val RCU_EXP_CPU_STALL_TIMEOUT 9999999
sed -i 's/> 300)/> 86400)/g; s/timeout, 300)/timeout, 86400)/g; s/= 300;/= 86400;/g' kernel/rcu/tree_stall.h
make olddefconfig

mkdir -p /mount/build/$1/
make bindeb-pkg -j $(nproc) LOCALVERSION=-svsm KDEB_COMPRESS=none
#KBUILD_OUTPUT=/mount/$1/../build
cd /mount/$1/../
rm -f /mount/build/$1/*
cp linux-headers-6.5.0* /mount/build/$1/linux-headers-6.5.0-svsm.deb
cp linux-image-!(*dbg*).deb /mount/build/$1/linux-image-6.5.0-svsm.deb
cp linux-libc-dev_6.5.0* /mount/build/$1/linux-libc-dev_6.5.0-svsm.deb
cd /mount
rm *.deb
rm linux-upstream*
# linux-libc-dev
