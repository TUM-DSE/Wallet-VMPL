obj-m = vmpl.o
KVERSION = $(shell uname -r)

all:
	make -C /lib/modules/$(KVERSION)/build M=$(PWD) modules
	gcc test.c -o test
clean:
	make -C /lib/modules/$(KVERSION)/build M=$(PWD) clean
	rm test

reload:	
	rmmod vmpl.ko | true
	insmod vmpl.ko
	
test: reload
	./test

	
