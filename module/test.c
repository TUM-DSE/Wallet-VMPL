#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>

#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <stddef.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <threads.h>
#include <pthread.h> 
#include <sched.h>
#include <sys/mman.h>
typedef signed long long int u64;

#include "vmpl.h"
//#define rax 1
//#define rcx 2
//#define rdx 3
//#define r8 4
//#define r9 5
struct svsm_call {
	void* caa;
	u64 rax;
	u64 rcx;
	u64 rdx;
	u64 r8;
	u64 r9;
};

struct mem memory;
int fd;


void alloc_memory(){
    u64 page_size = sysconf(_SC_PAGESIZE);
    int res;
    memory.pages = aligned_alloc(page_size, page_size);
    res = mlock(memory.pages,page_size);
    for(int i = 0; i< page_size; i++)
        ((uint8_t*)memory.pages)[i] = i;

    memory.stack = aligned_alloc(page_size, page_size);
    mlock(memory.stack,page_size);
    for(int i = 0; i< page_size; i++)
        ((uint8_t*)memory.stack)[i] = i;

    memory.vmsa = aligned_alloc(page_size, page_size);
    mlock(memory.vmsa,page_size);
    for(int i = 0; i< page_size; i++)
        ((uint8_t*)memory.vmsa)[i] = i;
}

void read_bin(){
    FILE* bin = fopen("./bin", "rb");
    memset(memory.pages,0,sysconf(_SC_PAGESIZE));
    int res = fread(memory.pages, 1, sysconf(_SC_PAGESIZE),bin);
    fclose(bin);
}


int print(void* args){
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(3, &cpuset);
    sched_setaffinity(0,sizeof(cpuset), &cpuset);
    while(1){
        sleep(5);
        for(int i = 0; i < 20; i++){
            printf("%02x  ",((uint8_t*)memory.stack)[i]);
        }
        printf("\n");
    }
    return 0;
}

int call_svsm(void* args){
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(4, &cpuset);
    sched_setaffinity(0,sizeof(cpuset), &cpuset);
    
    int res = -1;
    while(res == -1){
        res = ioctl(fd, VMPL_W2, &memory);
        printf("ioctl returned with %d\n",res);
        sleep(1);
    }
    return 0;
}




int main()
{
        
        int32_t value, number;
        fd = open("/dev/vmpl_device", O_RDWR);
        if(fd < 0) {
                printf("Cannot open device file...\n");
                return 0;
        }
        
        alloc_memory();
        read_bin();


        thrd_t print_thread, svsm_thread;

        thrd_create(&print_thread, print, NULL);
        thrd_create(&svsm_thread, call_svsm, NULL);
        
        thrd_join(print_thread,NULL);
        thrd_join(svsm_thread,NULL);

        close(fd);
        return 0;
}