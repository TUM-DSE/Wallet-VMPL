shopt -s extglob
set -x
virt-copy-in -a $1.qcow2 build/$2/linux-image-!(*dbg*).deb /
virt-copy-in -a $1.qcow2 build/$2/linux-headers-*.deb /
virt-copy-in -a $1.qcow2 build/$2/linux-libc-dev*.deb /
virt-customize --format qcow2 -a $1.qcow2 --run-command "dpkg -i /linux*"