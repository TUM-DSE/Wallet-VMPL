#include "request.h"

#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>

#include <vmpl.h>
 
int fd;

void* allocate_memory(uint32_t size){
    return aligned_alloc(PAGE_SIZE, size);
}
void free_memory(void* ptr){
    free(ptr);
}

int32_t request_init(){

    fd = open("/dev/vmpl_device", O_RDWR);
    if(fd < 0) {
            printf("Cannot open device file...\n");
            return -1;
    }
    return 0;
}
static inline _Bool is_aligned(const void *restrict pointer, size_t byte_count)
{ return (uintptr_t)pointer % byte_count == 0; }

int32_t handle_request(uint8_t* z, uint32_t zs, uint8_t* t, uint32_t ts, uint8_t* d, uint32_t ds) {

    //Simples case 
    // - Load Zygote 
    // - Load Trustlet
    // - Call with data
    // - Return result 
    printf("Test: %d\n",z[3]);
    struct monitor_call call;
    printf("al:\n");
    //Zygote
    printf("al: %d\n",is_aligned(z,1));
    call.type = createZygote;
    call.zygote_size = zs;
    call.zygote = z;

    return 0;

}

