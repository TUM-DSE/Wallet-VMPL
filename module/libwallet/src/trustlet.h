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
        } fileattr;
    };
};

enum invocation_type {
    normalInvocation = 0,
    requestFileattr,
};

enum invocation_return_type {
    invocationExit = 0,
    invocationGetValue = 1,
    invocationError = 2,
    guestRequestFileattr = 3,
};


int create_trustlet(const int zygote_id, char* func);
char* invoke_trustlet(const int trustlet_id, char* args, uint64_t output_size);
#endif // TRUSTLET_H_
