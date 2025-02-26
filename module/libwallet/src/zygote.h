#ifndef ZYGOTE_H_
#define ZYGOTE_H_
#include <stdint.h>
struct zygote_data {
    void* zygote_data[3];
    uint64_t size[3];
};

int create_zygote(const char* pal, const char* m, const char* os);
int delete_zygote(const int zygote_id);

#endif // ZYGOTE_H_
