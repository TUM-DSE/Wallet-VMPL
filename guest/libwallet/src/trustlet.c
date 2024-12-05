#include "trustlet.h"
#include <assert.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <string.h>
#include "memory.h"
#include "vmpl.h"

int create_trustlet(const int zygote_id/*TODO: Add parameters*/) {
    #ifndef NODEBUG
    printf("Trying to register Trustlet with Monitor\n");
    assert(con);
    #endif

    struct monitor_call call;
    call.type = createTrustlet;
    call.trustlet.zygote = zygote_id;

    int ret = ioctl(con, VMPL_WR, &call);

    #ifndef NODEBUG
    printf("Trustlet ID: %d\n", ret);
    #endif
    return ret;
}

void* invoke_trustlet(const int trustlet_id, const char* args){
    #ifndef NODEBUG
    assert(con);
    #endif
    const char* data;
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
