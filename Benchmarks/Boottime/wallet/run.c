#include <zygote.h>
#include <trustlet.h>
#include <monitor.h>
#include <sys/io.h>

#define BENCHMARK_PORT 0xF4

static inline void call(unsigned short value){
    outb(value, BENCHMARK_PORT);
}

int main() {


    if (ioperm(BENCHMARK_PORT, 1, 1)) {
        printf("Failed to get access to the benchmark port\n");
        return -1;
    }
    call(101);
    monitor_connect();
    call(102);
    call(103);
    int z = create_zygote("/root/Benchmarks/Boottime/wallet/libpal.so", "/root/Benchmarks/Boottime/wallet/manifest", "/root/Benchmarks/Boottime/wallet/libsysdb.so");
    call(104);
    call(105);
    int t = create_trustlet(z, "");
    call(106);
    call(107);
    invoke_trustlet(t, "", 0);
    call(108);
}
