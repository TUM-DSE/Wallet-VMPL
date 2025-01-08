#include "trustlet.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <string.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>


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

    invoke_data->function_arg.ptr = (void*)data;
    invoke_data->function_arg.size = strlen(args) + 1;

    uint64_t allocaction_size = 4096;
    if(output_size != 0){
        allocaction_size = output_size;
    }
    void* return_buffer = allocate_buffer(allocaction_size);

    invoke_data->result.ptr = return_buffer;
    invoke_data->result.size = allocaction_size;

    size_t guest_request_args_size = sizeof(struct guest_request_args);
    void* guest_request_args_buffer = allocate_buffer(allocaction_size);
    invoke_data->guest_request_args.ptr = guest_request_args_buffer;
    invoke_data->guest_request_args.size = guest_request_args_size;

    invoke_data->invokation_type = normalInvocation;

    call.invokation.data = invoke_data;
    call.invokation.data_size = sizeof(struct trustlet_invokation);

retry:
    int ret = ioctl(con, VMPL_WR, &call);

    #ifndef NODEBUG
    if(ret == invocationError)
        printf("Invokation failed\n");
    #endif

    if (ret == invocationGetValue) {
        return return_buffer;
    } else if (ret == guestRequestFileattr) {
        // handle guest request
        struct guest_request_args* arg = invoke_data->guest_request_args.ptr;
        struct stat st;
        stat(arg->fileattr.path, &st);
        arg->fileattr.size = st.st_size;
        arg->fileattr.mode = st.st_mode;
        invoke_data->invokation_type = requestFileattr;
        printf("Guest request: fileattr: path=%s, size=%ld, mode=%d\n", arg->fileattr.path, arg->fileattr.size, arg->fileattr.mode);
        goto retry;
    } else if (ret == guestRequestOpen) {
        struct guest_request_args* arg = invoke_data->guest_request_args.ptr;
        int fd = open(arg->fileattr.path, O_RDONLY);
        if (fd == -1) {
            printf("Failed to open file!\n");
        }
        arg->open.fd = fd;
        invoke_data->invokation_type = requestOpen;
        printf("Guest request: open: path=%s, fd=%d\n", arg->open.path, arg->open.fd);
        goto retry;
    } else if (ret == guestRequestRead) {
        struct guest_request_args* arg = invoke_data->guest_request_args.ptr;
        int fd = arg->read.fd;
        void* read_buffer = &arg->read.buf[0];
        int count = arg->read.count;
        if (count > sizeof(arg->read.buf)) {
            count = sizeof(arg->read.buf);
        }
        int read_bytes= pread64(fd, read_buffer, count, arg->read.offset);
        arg->read.count = read_bytes;
        invoke_data->invokation_type = requestRead;
        goto retry;
    }

    return NULL;
}
