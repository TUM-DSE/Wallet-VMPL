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
	rm test

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

t:
	gcc -g3 -I include/ -std=c11 app/t.c -lpthread -L include -l:libmy_crypto.a -o test

outb:
	gcc app/outb.c -o outb

test_elf:
	nasm -f elf64 -o  hello_elf.o hello_elf.asm
	ld -o simple_elf hello_elf.o
