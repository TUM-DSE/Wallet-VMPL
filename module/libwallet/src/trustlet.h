#ifndef TRUSTLET_H_
#define TRUSTLET_H_

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "monitor.h"

struct trustlet_invokation {
    void* trustlet_data[2];
    uint64_t trustlet_data_size[2];
};

int create_trustlet(const int zygote_id, char* func);
void* invoke_trustlet(const int trustlet_id, char* args, uint64_t output_size);
#endif // TRUSTLET_H_
