#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <sys/ioctl.h>
 
#define VMPL_WR _IOWR('a','a',struct svsm_call)

struct svsm_call {
	struct svsm_caa *caa;
	uint64_t rax;
	uint64_t rcx;
	uint64_t rdx;
	uint64_t r8;
	uint64_t r9;
};


int main()
{
        int fd;
        int32_t value, number;
        fd = open("/dev/vmpl_device", O_RDWR);
        if(fd < 0) {
                printf("Cannot open device file...\n");
                return 0;
        }
        struct svsm_call call;
        call.rax = (((uint64_t)5) << 32) | 0;

        int res = ioctl(fd, VMPL_WR, (void*) &call); 
 
        printf("Result: %p\n", call.caa);
        close(fd);
}