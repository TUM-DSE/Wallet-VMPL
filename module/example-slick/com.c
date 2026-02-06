#include <stdio.h>
#include <sys/io.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include "cpuid.c"

/* #define PORT 0xF4 */
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000
#define DATA_SHARED 0x38000000000

int main(int argc, char** argv) {

    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    char* shared = (char*)DATA_SHARED;
    finalize_zygote();
    int type = 0;
    int data_size = 64 * 1024;

    char* buf = malloc(2097152);

    trustlet_exit();

    while(1){
        if(input[0] != 'x'){
            trustlet_exit();
            strcpy(output, input);
            output[0] = 'p';
            trustlet_exit();
        } else {
            trustlet_exit();
            // Modify shared memory: change "AAAA" to "BBBB"
            memset(shared, 'B', 4);
            strcpy(output, input);
            output[0] = 'o';
            notify_monitor();
        }
    }
}
