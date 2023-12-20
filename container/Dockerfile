FROM ubuntu:22.04
RUN apt update && apt upgrade -y && apt install git libncurses-dev gawk flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf llvm zstd bc debhelper rsync cpio -y
COPY build.sh /build.sh
COPY user.sh /user.sh
CMD "./build.sh"