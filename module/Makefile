MODULE_NAME = vmpl
ccflags-y := -I$(src)/include
obj-m = vmpl.o
KVERSION = $(shell uname -r)
SRC = src/vmpl.c
${MODULE_NAME}-objs = $(SRC:.c=.o)

vmpl.ko: ${SRC}
	make -C /lib/modules/$(KVERSION)/build M=$(PWD) modules

all: vmpl.ko	
	gcc -I include/ -std=c11 app/test.c -lpthread -o test

clean:
	make -C /lib/modules/$(KVERSION)/build M=$(PWD) clean

reload:	
	rmmod vmpl.ko | true
	insmod vmpl.ko

test: reload bin
	./test "./bin"

test2: reload bin2
	./test "./bin2"

bin: programs/test.asm
	nasm -f bin test.asm -o bin/bin

write: programs/write.asm
	nasm -f bin programs/write.asm -o bin/write

ctest:
	gcc -c testcode.c -o testcode.o
	objcopy -O binary -j .text testcode.o binfile

test_create_cpu: 
	insmod vmpl.ko
	./test -

t: libwallet/libwallet.a
	gcc -g3 -I include/ -std=c11 app/t.c -lpthread -L include -l:libmy_crypto.a -Llibwallet/ -l:libwallet.a -Ilibwallet/src -o test

libwallet/libwallet.a:
	make -C libwallet/ libwallet.a
	make -C libwallet/ libwallet.so

outb:
	gcc app/outb.c -o outb

test_elf:
	nasm -f elf64 -o  hello_elf.o hello_elf.asm
	ld -o simple_elf hello_elf.o

install:
	mkdir -p /lib/modules/$(KVERSION)/build/certs/
	cp certs/* /lib/modules/$(KVERSION)/build/certs/
	make -C /lib/modules/$(KVERSION)/build M=$(PWD) modules_install
	depmod
	echo "vmpl" > /etc/modules-load.d/vmpl.conf
	modprobe vmpl


BOOT_PATH=/root/Benchmarks/Boottime

boottime_setup: vmpl.ko install
	cp ${BOOT_PATH}/wallet/service/* /etc/systemd/system/
	systemctl enable outb.service
	systemctl enable boottime.service
	cd libwallet/; NODEBUG=TRUE make libwallet.a
	cd ${BOOT_PATH}/wallet/; make run
	cd ${BOOT_PATH}/wallet/; make outb
	shutdown now

boottime_setup_vm:
	cp ${BOOT_PATH}/vm/service/* /etc/systemd/system/
	systemctl enable outb.service
	systemctl enable boottime.service
	cd ${BOOT_PATH}/vm/; make outb.so
	cd ${BOOT_PATH}/vm/; make outb
	shutdown now

ipc_setup: vmpl.ko install
	sleep 5
	shutdown now
