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
#include <inttypes.h>
#include <stdlib.h>
typedef signed long long int u64;
#define  PACKED __attribute__((__packed__)) 
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
struct PACKED attestation_report {
    uint32_t status;
    uint32_t report_size;
    uint8_t reserved[24];
    uint8_t report[];    
};

struct mem memory;
int fd;



//uint8_t att_buffer[4096];
int call_attest() {
    u64 page_size = sysconf(_SC_PAGESIZE);
    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
    for(int i = 0; i < page_size;i++){
        att_buffer[i] = i % 200;
    }
    printf("p: %p\n",att_buffer);
    sleep(1);
    cpu_set_t cpuset;
    struct monitor_call call;
    call.attestation_target = att_buffer;
    u64 ret;
    call.type = attest;
    ret = ioctl(fd,VMPL_WR,&call);
    printf("ret = %lld\n", ret);

    struct attestation_report* report = (struct attestation_report*)att_buffer;
    FILE* report_file = fopen("/root/report.txt","w");
    printf("FILE: %p\n",report_file);
    printf("SIZE: %ld\n",report->report_size);
    fwrite(report->report,report->report_size, 1,report_file);
    
    for(int i = 0; i<1216;i++){
        if(i == 64)
            printf("\n");
        printf("%" PRIu8 " ", att_buffer[i]);
    }
    free(att_buffer);
    printf("\n");
}


void monitor_init() {
    struct monitor_call call;
    call.type = initMonitor;
    int ret = ioctl(fd,VMPL_WR,&call);
    printf("Init called\n");

}

void single_exec(){
    struct monitor_call call; 
    uint8_t* att_buffer = aligned_alloc(4096, 4096);
    call.trustlet.size = 1;
    call.trustlet.trustlet_data = att_buffer;
    call.trustlet.zygote = 1;
    call.type = createTrustlet;
      int ret = ioctl(fd,VMPL_WR,&call);
    printf("Init called\n");  
}

int main(int argc, char** argv)
{
        int32_t value, number;


        fd = open("/dev/vmpl_device", O_RDWR);
        if(fd < 0) {
                printf("Cannot open device file...\n");
                return -1;
        }
        monitor_init();
        single_exec();
        int i = 0;
        //while(1){
            //printf("Test: %d\n", i++);
        //}
        //call_attest();

        /*
        if(argc < 2) {
            setup_schal();
            printf("Setup done.\nStarting Process");
            create_vcpu(3,3);
            printf("Done");
            goto close_;
        }

        if(strcmp(argv[1], "-t") == 0){
            measure_vmpl_rtt();
            goto close_;
        }
        /*if(strcmp(argv[1], "-p") == 0){
            test_paging();
            goto close_;
        }
        if(strcmp(argv[1], "-s") == 0){
            setup_schal();
            printf("Done!\n");
            goto close_;
        }
        if(strcmp(argv[1], "-c") == 0){
            create_all_vcpus();
            printf("Done!\n");
            goto close_;
        }

        alloc_memory();
        read_bin(argv[1]);



        thrd_t print_thread, svsm_thread;

        thrd_create(&print_thread, print, NULL);
        thrd_create(&svsm_thread, run_single_exec, (void*)4);
        
        thrd_join(print_thread,NULL);
        thrd_join(svsm_thread,NULL);
        */
close_:
        printf("Close");
        close(fd);
        return 0;
}
