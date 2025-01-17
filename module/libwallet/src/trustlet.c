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

#include <sys/syscall.h>
#include <dirent.h>
struct linux_dirent64 {
    uint64_t        d_ino;    /* 64-bit inode number */
    uint64_t        d_off;    /* Not an offset; see getdents() */
    unsigned short  d_reclen; /* Size of this dirent */
    unsigned char   d_type;   /* File type */
    char            d_name[]; /* Filename (null-terminated) */
};

#define INIT_CREATE_TRUSTLET(id, data, size)\
    do {                                    \
    call.type = createTrustlet;             \
    call.trustlet.zygote = id;              \
    call.trustlet.trustlet_data = data;     \
    call.trustlet.size = size;              \
    } while(0)

static int is_dot_or_dotdot(const char *name) {
    return name[0] == '.' && (name[1] == '\0' || (name[1] == '.' && name[2] == '\0'));
}

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
    void* mmap_read_buffer = allocate_buffer(4096);

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
    void* return_buffer_address = NULL;
    int ret = ioctl(con, VMPL_WR, &call);

    #ifndef NODEBUG
    if(ret == invocationError)
        printf("Invokation failed\n");
    #endif

    if (ret == invocationGetValue) {
        return_buffer_address = return_buffer;
    } else if (ret == guestRequestFileattr) {
        // handle guest request
        struct guest_request_args* arg = invoke_data->guest_request_args.ptr;
        struct stat st;
        int ret = stat(arg->fileattr.path, &st);
        arg->fileattr.ret = ret;
        arg->fileattr.size = st.st_size;
        arg->fileattr.mode = st.st_mode;
        invoke_data->invokation_type = requestFileattr;
        printf("Guest request: fileattr: ret=%d, path=%s, size=%ld, mode=%d\n", arg->fileattr.ret, arg->fileattr.path, arg->fileattr.size, arg->fileattr.mode);
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
        int read_bytes = 0;

        if (arg->read.offset == (uint64_t)-1) {
            // dir read
            // XXX: code adopted from read_dir() of linux pal of gramine
            char *buf = read_buffer;
            char dirbuf[1024];
            // gcc does not provide a wrapper for getdents64
            int size = syscall(SYS_getdents64, fd, dirbuf, sizeof(dirbuf));
            if (size == -1) {
                printf("Failed to read dir!\n");
                // TODO: handle error
            } else {
                char *ptr = dirbuf;
                int remaining = size;
                printf("Guest requet: dire_read: %d bytes for dentry\n", size);
                while(remaining > 0) {
                    struct linux_dirent64* dirent = (struct linux_dirent64*)ptr;
                    if (is_dot_or_dotdot(dirent->d_name)) {
                        goto skip;
                    }

                    int is_dir = dirent->d_type == DT_DIR;
                    size_t len = strlen(dirent->d_name);

                    if (len + 1 + (is_dir ? 1 : 0) > count) {
                        // seek back fd so that next read will read the same dentry
                        lseek(fd, -remaining, SEEK_CUR);
                        break;
                    }

                    memcpy(buf, dirent->d_name, len);
                    if (is_dir) {
                        buf[len++] = '/';
                    }
                    buf[len++] = '\0';

                    buf += len;
                    read_bytes += len;
                    count -= len;
                    if (count == 0) {
                        break;
                    }
skip:
                    ptr += dirent->d_reclen;
                    remaining -= dirent->d_reclen;
                }
            }
        } else {
            // file read
            read_bytes = pread(fd, read_buffer, count, arg->read.offset);
        }
        arg->read.count = read_bytes;
        invoke_data->invokation_type = requestRead;
        printf("Guest request: read: fd=%d, offset=%ld, count=%lu\n", fd, arg->read.offset, arg->read.count);
        goto retry;
    } else if (ret == guestRequestMmap) {
        struct guest_request_args* arg = invoke_data->guest_request_args.ptr;
        printf("Guest request: mmap: fd=%d, size=%ld, offset=%ld, addr_offset=%ld\n", (int)arg->mmap.fd, arg->mmap.size, arg->mmap.offset, arg->mmap.addr_offset);
        void *addr = NULL;
        memset(mmap_read_buffer, 0, 4096);
        int ret = pread(arg->mmap.fd, mmap_read_buffer, 4096, arg->mmap.offset + arg->mmap.addr_offset);
        if (ret == -1) {
            printf("Failed to read file!\n");
        }
        arg->mmap.buf_addr = (uint64_t)mmap_read_buffer;
        invoke_data->invokation_type = requestMmap;
        goto retry;
    }

exit:

    free(mmap_read_buffer);
    return return_buffer_address;
}

void create_channel(const int trustlet_id_1, const int trustlet_id_2){
    #ifndef NODEBUG
    assert(con);
    #endif

    printf("Creating channel between %d and %d\n", trustlet_id_1, trustlet_id_2);

    struct monitor_call call;
    call.type = createChannel;
    call.channel.trustlet_id_1 = trustlet_id_1;
    call.channel.trustlet_id_2 = trustlet_id_2;
    ioctl(con, VMPL_WR, &call);
}
