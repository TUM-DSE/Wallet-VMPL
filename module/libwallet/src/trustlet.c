#include "trustlet.h"
#include <assert.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <string.h>
#include <stdlib.h>
#include "memory.h"
#include "vmpl.h"

#define INIT_CREATE_TRUSTLET(id, data, size)\
    do {                                    \
    call.type = createTrustlet;             \
    call.trustlet.zygote = id;              \
    call.trustlet.trustlet_data = data;     \
    call.trustlet.size = size;              \
    } while(0)

static void allocate_trustlet_struct(struct trustlet_invokation** z){
    uint8_t* buf = aligned_alloc(4096, 4096);
    for(int i =0;i <4096;i++)
        buf[i] = 0;
    *z = (void*)buf;
}

int create_trustlet(const int zygote_id, char* func) {
    #ifndef NODEBUG
    printf("Trying to register Trustlet with Monitor\n");
    assert(con);
    #endif
    uint64_t size = strlen(func);
    char* out;
    if(func){
        load_data(func, &out);
    } else {
        out = NULL;
    }
    struct monitor_call call;

    INIT_CREATE_TRUSTLET(zygote_id, out, size);

    int ret = ioctl(con, VMPL_WR, &call);

    #ifndef NODEBUG
    printf("Trustlet ID: %d\n", ret);
    #endif
    return ret;
}


char* invoke_trustlet(const int trustlet_id, char* args, uint64_t output_size){
    #ifndef NODEBUG
    assert(con);
    #endif
    char* data;
    load_data(args, &data);

    struct trustlet_invokation* invoke_data;

    allocate_trustlet_struct(&invoke_data);

    struct monitor_call call;

    call.type = invokeTrustlet;
    call.invokation.process_id = trustlet_id;

    invoke_data->trustlet_data[0] = (void*)data;
    invoke_data->trustlet_data_size[0] = strlen(args);

    uint64_t allocaction_size = 4096;
    if(output_size != 0){
        allocaction_size = output_size;
    }
    void* return_buffer = allocate_buffer(allocaction_size);

    invoke_data->trustlet_data[1] = return_buffer;
    invoke_data->trustlet_data_size[1] = allocaction_size;

    call.invokation.data = invoke_data;
    call.invokation.data_size = sizeof(struct trustlet_invokation);

    int ret = ioctl(con, VMPL_WR, &call);

    #ifndef NODEBUG
    if(ret)
        printf("Invokation failed\n");
    else
        printf("Result: %s\n", (char*)return_buffer);
    #endif

    if(ret)
        return return_buffer;

    return NULL;
}
