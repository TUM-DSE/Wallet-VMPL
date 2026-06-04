#include <stdio.h>
#include <sys/io.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include "cpuid.c"
#include "dpdk_stub.h"

#define PORT 0xF4
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000

#define println(...) do { fprintf(stdout, __VA_ARGS__); fflush(stdout); } while(0)

int main(int argc, char** argv) {
    /* uint32_t lo, hi; */
    /* __asm__ volatile("rdmsr" : "=a"(lo), "=d"(hi) : "c"(0x1b)); */
    /* __asm__ volatile("cli"); */
    /**/
    /* uint64_t rflags; */
    /* __asm__ volatile("pushfq; popq %0" : "=r"(rflags)); */
    /* println("rflags=0x%lx", rflags); */


    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    finalize_zygote();
    int type = 0;
    int data_size = 64 * 1024;

    char* buf = malloc(2097152);

    trustlet_exit();

    while(1){
        if(input[0] != 'x'){
            trustlet_exit();
            strcpy(output, input);
            output[1] += 1;
            notify_monitor();
        } else {
            trustlet_exit();
            strcpy(output, input);
            output[2] += 1;
            notify_monitor();
        }
    }
}
