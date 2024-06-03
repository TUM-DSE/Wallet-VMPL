#ifndef REQUEST_H
#define REQUEST_H
#include <stdint.h>
#define PAGE_SIZE 4096
int32_t handle_request(uint8_t* z, uint32_t zs, uint8_t* t, uint32_t ts, uint8_t* d, uint32_t ds);
int32_t request_init();
void* get_monitor_report();
void* allocate_memory(uint32_t size);
void free_memory(void* ptr);
#endif