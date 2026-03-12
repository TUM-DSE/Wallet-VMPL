#include <stdio.h>
#include <sys/io.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include "cpuid.c"
#include "dpdk_stub.h"

#define PORT 0xF4
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000

void main_default(bool suppress_output) {
    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    trustlet_exit();

    while (1) {
        strcpy(output, input);

        if (suppress_output) {
            output[1] += 1;
            trustlet_exit();
        } else {
            // Only the second trustlet is a privileged one that can run rdmsr
            // check that we are in ring 0. Faults otherwise.
            uint32_t lo, hi;
            __asm__ volatile("rdmsr" : "=a"(lo), "=d"(hi) : "c"(0x1b));

            output[2] += 1;
            notify_monitor();
        }

    }
}

int main(int argc, char** argv) {

    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    finalize_zygote();
    int type = 0;
    int data_size = 64 * 1024;

    char* buf = malloc(2097152);

    trustlet_exit();

    if(input[0] != 'x'){
        bool suppress_output = true;
        main_default(suppress_output);
    } else {
        bool suppress_output = false;
        main_default(suppress_output);
    }
}
