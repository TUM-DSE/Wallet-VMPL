#include "zygote.h"
#include "memory.h"

#include "monitor.h"
#include <stdio.h>
#include <stdlib.h>
#include <linux/ioctl.h>
#include <sys/ioctl.h>
#include <assert.h>
#include "vmpl.h"

#define PAGE_SIZE 4096

static void allocate_zygote_struct(struct zygote_data** z){
    uint8_t* buf = aligned_alloc(4096, 4096);
    for(int i =0;i <4096;i++)
        buf[i] = 0;
    *z = (void*)buf;
}



int create_zygote(const char* pal, const char* m, const char* os) {
    uint8_t* data;
    uint64_t size;
    load_file(pal, &data, &size);

    uint8_t* manifest;
    uint64_t manifest_size;
    load_file(m, &manifest, &manifest_size);

    uint8_t* libos;
    uint64_t libos_size;
    load_file(os, &libos, &libos_size);

    struct zygote_data* z;
    allocate_zygote_struct(&z);

    z->zygote_data[0] = data;
    z->size[0] = size;
    z->zygote_data[1] = manifest;
    z->size[1] = manifest_size;
    z->zygote_data[2] = libos;
    z->size[2] = libos_size;

    struct monitor_call call;
    call.zygote.zygote_data = (void*)z;
    call.zygote.size = PAGE_SIZE;
    call.type = createZygote;
    #ifndef NODEBUG
    assert(con);
    #endif
    int ret = ioctl(con, VMPL_WR, &call);
    #ifndef NODEBUG
    printf("Zygote ID: %d\n", ret);
    #endif
    return ret;
}

int delete_zygote(const int zygote_id) {
    struct monitor_call call;
    call.type = deleteZygote;
    call.process_id = zygote_id;
#ifndef NODEBUG
    assert(con);
    printf("Delete zygote %d\n", zygote_id);
#endif
    return ioctl(con, VMPL_WR, &call);
}
