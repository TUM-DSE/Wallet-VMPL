#include <stdio.h>
#include <sys/io.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include "cpuid.c"

#define PORT 0xF4
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000

int main(int argc, char** argv) {

    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    finalize_zygote();
    int type = 0;
    int data_size = 64 * 1024;

    char* buf = malloc(2097152);

    trustlet_exit();

    if(input[0] != 'x'){
        trustlet_exit();
        while(1){
            strcpy(output, input);
            output[1] += 1;
            notify_monitor();
        }
    } else {
        trustlet_exit();
        while(1){
            strcpy(output, input);
            output[2] += 1;
            notify_monitor();
        }
    }
}
