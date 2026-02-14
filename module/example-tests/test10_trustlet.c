#include <stdio.h>
#include <sys/io.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include <time.h>
#include "cpuid.c"
#include "util.h"

#define PORT 0xF4
#define DATA_IN 0x28000000000
#define DATA_OUT 0x30000000000
#define DATA_SHARED 0x38000000000
#define DATA_SIZE 16

#define println(...) do { fprintf(stdout, __VA_ARGS__); fflush(stdout); } while(0)

void hexdump(const void *data, size_t size) {
    for (size_t i = 0; i < size; i++) printf("%02x ", ((unsigned char *)data)[i]);
    println("");
}

// CPU frequency in GHz - used to correct clock_gettime which returns TSC cycles
#define CPU_GHZ 2.0

// build our own delay, because gramine's sleep is unimplemented
void delay(uint64_t nsecs) {
    // clock_gettime returns TSC cycles misinterpreted as usec, then converted to nsec
    // Effective value is cycles * 1000, so divide by (CPU_GHZ * 1000) to get real nsec
    struct timespec ts;
    int ret = clock_gettime(CLOCK_MONOTONIC, &ts);
    println("delay: clock_gettime returned %d, tv_sec=%ld, tv_nsec=%ld", ret, ts.tv_sec, ts.tv_nsec);
    uint64_t start = (ts.tv_sec * 1000000000ULL + ts.tv_nsec) / (CPU_GHZ * 1000);
    uint64_t end = start + nsecs;
    println("delay: start=%lu, end=%lu, waiting for %lu ns", start, end, nsecs);
    while (1) {
        ret = clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t now = (ts.tv_sec * 1000000000ULL + ts.tv_nsec) / (CPU_GHZ * 1000);
        if (now >= end) {
            println("delay: done, now=%lu", now);
            break;
        }
    }
}

void main_shm() {
    char* shared = (char*)DATA_SHARED;
    struct buffer* buf = (struct buffer*)shared; // TODO
    size_t buf_used = 0;
    trustlet_exit();

    while (1) {
        buf_used = trustlet_rx(buf);
        buf->data[3] += 1;
        trustlet_tx(buf, buf_used);

        notify_monitor();
    }
}

void main_default(bool suppress_output) {
    char* input = (char*)DATA_IN;
    char* output = (char*)DATA_OUT;
    trustlet_exit();

    while (1) {
        memcpy(output, input, DATA_SIZE);

        if (suppress_output) {
            output[1] += 1;
            printf("Trustlet processed: ");
            hexdump(output, DATA_SIZE);
            trustlet_exit();
        } else {
            output[2] += 1;
            printf("Trustlet processed: ");
            hexdump(output, DATA_SIZE);
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

    if(input[0] == 's'){
        main_shm();
    } else if(input[0] == 'x'){
        bool suppress_output = false;
        main_default(suppress_output);
    } else {
        bool suppress_output = true;
        main_default(suppress_output);
    }
}
