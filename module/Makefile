obj-m = vmpl.o
KVERSION = $(shell uname -r)

all:
	make -C /lib/modules/$(KVERSION)/build M=$(PWD) modules
	gcc -std=c11 test.c -lpthread -o test
clean:
	make -C /lib/modules/$(KVERSION)/build M=$(PWD) clean
	rm test

reload:	
	rmmod vmpl.ko | true
	insmod vmpl.ko
	
test: reload bin
	./test "./bin"

test2: reload bin2
	./test "./bin2"

bin: test.asm
	nasm -f bin test.asm -o bin

bin2: test2.asm
	nasm -f bin test.asm -o bin2

ctest:
	gcc -c testcode.c -o testcode.o
	objcopy -O binary -j .text testcode.o binfile
	
page: reload bin
	./test -p