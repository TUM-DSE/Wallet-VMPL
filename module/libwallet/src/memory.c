#include "memory.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <string.h>
#define PAGE_SIZE 4096
#define ROUND_UP_SIZE(x) x + PAGE_SIZE - (x % PAGE_SIZE)
void load_file(const char* path, uint8_t** data, uint64_t* buf_size) {
    FILE* file = fopen(path, "r");
    #ifndef NODEBUG
    assert(file);
    #endif
    fseek(file, 0L, SEEK_END);
    uint64_t size = ftell(file);
    rewind(file);
    uint64_t actual_size = ROUND_UP_SIZE(size);
    uint8_t* buf = aligned_alloc(PAGE_SIZE, actual_size);
    for(int i = 0; i < actual_size; i++)
        buf[i] = 0;
    size_t read_len = fread((void*)buf, 1, size, file);
    if(read_len != size) {
        fprintf(stderr, "Failed to load entire file %ld != %ld", read_len, size);
        exit(-1);
    }
    *data = buf;
    *buf_size = actual_size;
}

void load_data(char* in, char** out){
    uint64_t size = strlen(in);
    uint64_t actual_size = ROUND_UP_SIZE(size);
    uint8_t* buf = aligned_alloc(PAGE_SIZE, actual_size);
    for(int i = 0; i < size; i++)
        buf[i] = in[i];
    *out = buf;
}

void load_data_with_len(char* in, char** out, uint64_t len){
    uint64_t actual_size = ROUND_UP_SIZE(len);
    uint8_t* buf = aligned_alloc(PAGE_SIZE, actual_size);
    for(int i = 0; i < len; i++)
        buf[i] = in[i];
    *out = buf;
}

void* allocate_buffer(uint64_t size) {
    uint64_t actual_size = ROUND_UP_SIZE(size);
    uint8_t* buf = aligned_alloc(PAGE_SIZE, actual_size);
    for(int i = 0; i < actual_size; i++){
        buf[i] = 0;
    }
    return buf;
}
