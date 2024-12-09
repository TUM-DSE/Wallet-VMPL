#ifndef MEMORY_H_
#define MEMORY_H_

#include <stdint.h>

void load_file(const char* path, uint8_t** data, uint64_t* buf_size);
void load_data(char* in, char** out);
void* allocate_buffer(uint64_t size);
#endif // MEMORY_H_
