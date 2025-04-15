#include <stddef.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include "../../../../module/include/my_crypto.h"
//gcc -m=native -O3 measure.c -L./ -l:libmy_crypto.a
uint64_t measure(const char* file){

    int fd = open(file, O_RDONLY);
    FILE* f = fdopen(fd, "rb");

    fseek(f, 0L, SEEK_END);
    size_t size = ftell(f);
    rewind(f);
    uint8_t* buf = malloc(size);

    size_t read_size = read(fd, buf, size);
    if(read_size < size){
        fprintf(stderr,"Failed to read file");
        exit(-1);
    }
    uint8_t hash[64];
    struct timespec start, end;
    timespec_get(&start, TIME_UTC);
    my_SHA512(buf, size, hash);
    timespec_get(&end, TIME_UTC);
    time_t tstart = ((uint64_t)start.tv_sec * 1000000000 + start.tv_nsec);
    time_t tend = ((uint64_t)end.tv_sec * 1000000000 + end.tv_nsec);
    return tend - tstart;
}

int main() {
    FILE* f = fopen("result.csv","w");
    const char* csv_header = "file,time\n";
    fprintf(f,csv_header);
    for(int i = 0; i < 10; i++) {
        uint64_t time = measure("../../../linux/vmlinux");
	fprintf(f,"kernel,%ld\n",time);
    }
}
