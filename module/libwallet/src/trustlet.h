#ifndef TRUSTLET_H_
#define TRUSTLET_H_

#include <assert.h>
#include <stdio.h>
#include "monitor.h"

int create_trustlet(const int zygote_id);
void* invoke_trustlet(const int trustlet_id, const char* args);
#endif // TRUSTLET_H_
