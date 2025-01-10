#ifndef TRUSTLET_H_
#define TRUSTLET_H_

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "monitor.h"

struct data {
    void* ptr;
    uint64_t size;
};

struct trustlet_invokation {
    uint64_t invokation_type;
    struct data function_arg;
    struct data result;
    struct data guest_request_args;
};

struct guest_request_args {
    union {
        struct {
            char path[256];
            uint64_t size;
            uint32_t mode;
            int32_t ret;
        } fileattr;
        struct {
            char path[256];
            uint32_t fd;
        } open;
        struct {
            char buf[1024];
            uint64_t count;
            uint64_t offset;
            uint32_t fd;
        } read;
        struct {
            uint64_t fd; // use uint64_t so that the monitor
                         // can access all fields using u64
                         // sice
            uint64_t offset;
            uint64_t size;
            uint64_t addr_offset;
            uint64_t buf_addr;
        } mmap;
    };
};

enum invocation_type {
    normalInvocation = 0,
    requestFileattr,
    requestOpen,
    requestRead,
    requestMmap,
};

enum invocation_return_type {
    invocationExit = 0,
    invocationGetValue = 1,
    invocationError = 2,
    guestRequestFileattr = 3,
    guestRequestOpen = 4,
    guestRequestRead = 5,
    guestRequestMmap = 6,
};


int create_trustlet(const int zygote_id, char* func);
char* invoke_trustlet(const int trustlet_id, char* args, uint64_t output_size);
#endif // TRUSTLET_H_
