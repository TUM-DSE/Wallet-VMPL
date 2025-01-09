#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char* channel_input = (char *)0x28000000000ULL;
const char* channel_output = (char *)0x30000000000ULL;

static void cpuid(unsigned int *eax, unsigned int *ebx, unsigned int *ecx, unsigned int *edx) {
    __asm__ __volatile__("cpuid"
                         : "=a" (*eax), "=b" (*ebx), "=c" (*ecx), "=d" (*edx)
                         : "a" (*eax), "c" (*ecx));
}

static void pal_svsm_get_result(){
    unsigned int eax=0, ebx=0, ecx=0, edx=0;
    eax = 0x4FFFFFF8;
    cpuid(&eax, &ebx, &ecx, &edx);
}

int main(int argc, char **argv) {
    int id = -1;
    if (argc > 1) {
        id = atoi(argv[1]);
    }
    printf("[id=%d] Channel test\n", id);

    // XXX: we assume that the channel_input is properly null-terminated
    printf("[id=%d] Input: %s\n", id, channel_input);

    char buf[128] = {};
    snprintf(buf, sizeof(buf), "output from id=%d: input='%s'", id, channel_input);
    memcpy((void *)channel_output, buf, strlen(buf) + 1);

    pal_svsm_get_result();

    return 0;
}
