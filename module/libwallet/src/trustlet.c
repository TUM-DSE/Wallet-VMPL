#include "trustlet.h"
#include <assert.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <string.h>
#include "memory.h"
#include "vmpl.h"

#define INIT_CREATE_TRUSTLET(id, data, size)\
    do {                                    \
    call.type = createTrustlet;             \
    call.trustlet.zygote = id;              \
    call.trustlet.trustlet_data = data;     \
    call.trustlet.size = size;              \
    } while(0)

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

void* invoke_trustlet(const int trustlet_id, char* args){
    #ifndef NODEBUG
    assert(con);
    #endif
    char* data;
    load_data(args, &data);

    struct monitor_call call;

    call.type = invokeTrustlet;
    call.invokation.process_id = trustlet_id;

    call.invokation.input_data = (void*)data;
    call.invokation.input_data_size = strlen(args);

    int ret = ioctl(con, VMPL_WR, &call);

    #ifndef NODEBUG
    if(ret)
        printf("Invokation failed\n");
    else
        printf("Result: %s\n", (char*)data);
    #endif

    if(ret)
        return data;

    return NULL;
}
