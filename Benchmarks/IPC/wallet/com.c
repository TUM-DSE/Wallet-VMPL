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
    fprintf(stderr, "Start %d", argc);
    int read_write = 0;
    char* buf = malloc(2097152);


    if(argc > 1) {
        read_write = 1;
    }

    trustlet_exit();

    while(1) {
        if(read_write == 0) {
            call_outb_with_value(200);
            strcpy(output, input);
            trustlet_exit();
        } else {
            //call_outb_with_value(201);
            strcpy(buf, input);
            call_outb_with_value(202);

            uint64_t size = strlen(buf);
            sprintf(output, "strlen = %d",size);
            notify_monitor();
        }
    }


}
