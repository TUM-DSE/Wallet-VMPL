#define _GNU_SOURCE

#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <zygote.h>
#include <trustlet.h>
#include <monitor.h>
#include <time.h>
#include <stdint.h>
#include <sys/time.h>
#include <pthread.h>
#include <sched.h>
#include <unistd.h>
#include <stdio.h>
#include <errno.h>
#include <sys/mman.h>

#include "util.h"
#include "util_run.h"
#include "dpdk_stub.h"

// like test6, but with shm between trustlet and guest OS
// needs
// * /etc/default/grub GRUB_CMDLINE_LINUX="isolcpus=1 irqaffinity=0 nohz=on nohz_full=1" update-grub

#define SHARED_SIZE 4096

int main() {
    // with wallet.Wallet() as w:
    monitor_connect();

    int input_size = 16;

    int chain_len = 2;
    int chains[] = {2};
    int chains_len = 1;

    int iterations = 1;

    int zygotes[2];
    int trustlets[2];

    // for i in range(chain_len):
    //     zygotes.append(w.create_zygote("../libpal.so", "test4_manifest", "../libsysdb.so"))
    for (int i = 0; i < chain_len; i++) {
        zygotes[i] = create_zygote("../libpal.so", "test10_manifest", "../libsysdb.so");
    }

    // for i in range(chain_len):
    //     trustlets.append(zygotes[i].create_trustlet("./empty.py"))
    for (int i = 0; i < chain_len; i++) {
        trustlets[i] = create_trustlet(zygotes[i], "./empty.py");
    }

    // Allocate and register shared memory
    void *target_addr = (void *)0x38000000000ULL;
    struct buffer *shared = mmap(target_addr, SHARED_SIZE,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
        -1, 0);
    if (shared == MAP_FAILED) {
        printf("mmap at %p failed: %s\n", target_addr, strerror(errno));
        return -1;
    }
    shared->data[0] = 'I';
    if (!create_shared_memory(trustlets[1], shared, SHARED_SIZE)) {
        printf("Failed to create shared memory\n");
        return -1;
    }
    printf("Shared memory registered\n");

    // input_data = b"a" * (input_size - 1) + b"\00"
    char input_data[16];
    memset(input_data, 'a', input_size - 1);
    input_data[input_size - 1] = '\0';

    // for t in trustlets:
    //     t.invoke_trustlet(input_data, len(input_data))
    for (int t = 0; t < chain_len; t++) {
        invoke_trustlet(trustlets[t], input_data, input_size);
    }

    int chained = 0;

    // for i in chains:
    for (int idx = 0; idx < chains_len; idx++) {
        int i = chains[idx];

        // #Create chains
        // for c in range(chained,i - 1):
        //     trustlets[c].create_channel(trustlets[c+1])
        for (int c = chained; c < i - 1; c++) {
            // create_channel(trustlets[c], trustlets[c+1]);
        }
        chained += i - chained - 1;

        // #Prepair input data
        // input_data = b"b" * (input_size - 1) + b"\00"
        memset(input_data, 'b', input_size - 1);
        input_data[input_size / 2] = '\0';
        input_data[input_size - 1] = '\0';

        // #Setup Trustlets
        // for t in range(i - 1):
        //     trustlets[t].invoke_trustlet(b"a", 0)
        for (int t = 0; t < i - 1; t++) {
            // Transfer nodes (input->output)
            invoke_trustlet(trustlets[t], "a", 0);
        }
        // trustlets[i - 1].invoke_trustlet(b"s", 0)
        // End node - use shm mode
        invoke_trustlet(trustlets[i - 1], "s", 0);

        // for _ in range(iterations):
        for (int iter = 0; iter < iterations; iter++) {
            // start = time.time_ns()
            struct timespec ts;
            clock_gettime(CLOCK_MONOTONIC, &ts);
            uint64_t start = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

            // Write to shared memory, then invoke with 's' mode
            memcpy(shared->data, input_data, input_size);
            driver_tx(shared, input_size);
            time_t now = time(NULL);
            struct tm *tm = localtime(&now);
            printf("Time: %02d:%02d:%02d\n", tm->tm_hour, tm->tm_min, tm->tm_sec);
            struct threaded_invoke_handle* handle = threaded_invoke(trustlets[1], 1, "s", 0);
            /* invoke_trustlet(trustlets[1], "s", 0); */
            printf("Waiting for trustlet to finish on CPU 1");
            sleep(1);
            printf("."); fflush(stdout);
            sleep(1);
            printf("."); fflush(stdout);
            sleep(1);
            printf(".\n"); fflush(stdout);
            char* _res = threaded_join(handle);
            threaded_free(handle);
            size_t _ = driver_rx(shared);
            char* res = shared->data;
            hexdump(input_data, input_size);
            hexdump(res, input_size);

            // // for t in range(1, i - 1):
            // //     trustlets[t].invoke_trustlet(b"", 0)
            // for (int t = 1; t < i - 1; t++) {
            //     invoke_trustlet_bin(trustlets[t], input_data, input_size, 0);
            // }

            // // res = trustlets[i - 1].invoke_trustlet(b"", len(input_data))
            // res = invoke_trustlet_bin(trustlets[i - 1], input_data, input_size, input_size);

            // // print(f"Output: {res}")
            // printf("Output: %s\n", res);

            // expected = bytearray(input_data)
            char expected[16];
            memcpy(expected, input_data, input_size);

            // expected[2] += 1
            expected[3] += 1;
            // // expected[1] += i-1
            // expected[1] += i - 1;
            // expected = expected.decode('ascii').strip('\x00')
            // (in C, expected is already a string, strip null not needed for comparison)

            // print(expected)
            printf("%s\n", expected);
            hexdump(expected, input_size);
            hexdump(res, input_size);

            clock_gettime(CLOCK_MONOTONIC, &ts);
            uint64_t end = ts.tv_sec * 1000000000ULL + ts.tv_nsec;
            printf("Iteration %d took %.3f s\n", iter, 1.0 * (end - start) / 1e9);

            // assert res == expected
            assert(memcmp(res, expected, input_size) == 0);
        }
    }

    return 0;
}
