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
	
test: reload
	./test

asm: test.asm
	nasm -f bin test.asm -o bin
