#!/bin/bash
#mount -t 9p -o trans=virtio  mo mod/ -oversion=9p2000.L
set -x
shopt -s extglob
qemu-img create -f qcow2 -o preallocation=metadata $2.qcow2 ${4}G
virt-resize --format qcow2 --resize /dev/sda1=+7G $1.qcow2 $2.qcow2
virt-customize -a $2.qcow2 --run-command 'grub-install /dev/sda'
virt-customize --format qcow2 -a $2.qcow2 --root-password password:root --run-command "mkdir /root/.ssh" --hostname $2_vmpl
virt-copy-in -a $2.qcow2 build/$3/linux-image-!(*dbg*).deb /
virt-copy-in -a $2.qcow2 build/$3/linux-headers-*.deb /
virt-copy-in -a $2.qcow2 build/$3/linux-libc-dev*.deb /
virt-copy-in -a $2.qcow2 container/99_config.yaml /etc/netplan/
virt-copy-in -a $2.qcow2 container/authorized_keys /root/.ssh
for filename in container/guestkeys/*; do
    virt-copy-in -a $2.qcow2 $filename /etc/ssh/
done
virt-copy-in -a $2.qcow2 container/guestkeys/ /
virt-copy-in -a $2.qcow2 container/sshd_config /etc/ssh/
virt-copy-in -a $2.qcow2 container/fstab /etc/
virt-copy-in -a $2.qcow2 container/nasm /bin/
virt-copy-in -a $2.qcow2 scripts/grub /etc/default/
virt-customize --format qcow2 -a $2.qcow2 --run-command "systemctl disable systemd-timesyncd"\
             --run-command "chmod 700 /etc/netplan/99_config.yaml"\
             --run-command "chown root:root /root/.ssh/*"\
             --run-command "netplan apply"\
	     --run-command "sudo systemctl mask network-online.target  network-pre.target  network.target cloud-final.service cloud-config.service open-iscsi.service iscsid.service networkd-dispatcher.service"\
             --run-command "systemctl disable systemd-networkd-wait-online.service"\
             --run-command "apt autoremove --purge snapd -y"\
             --run-command "apt-mark hold snapd"\
             --run-command "dpkg -i /linux-*.deb"\
             --install "gcc" \
             --install "make" \
	     --run-command "grub-mkconfig -o /boot/grub/grub.cfg"
