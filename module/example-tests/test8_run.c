#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <zygote.h>
#include <trustlet.h>
#include <monitor.h>
#include <time.h>
#include <stdint.h>

// like test6, but we make it a simple packet throughput test

#define DEBUG 0

#if DEBUG
#define debug
#else
#define debug if(0)
#endif

#define INPUT_SIZE 64

void hexdump(const void *data, size_t size) {
    for (size_t i = 0; i < size; i++) {
        printf("%02x ", ((unsigned char *)data)[i]);
        if ((i + 1) % 16 == 0) printf("\n");
    }
    if (size % 16 != 0) printf("\n");
}

int main() {
    // with wallet.Wallet() as w:
    monitor_connect();

    int input_size = INPUT_SIZE;

    int chain_len = 2;
    int chains[] = {2};
    int chains_len = 1;

    int iterations = 2000 * 5; // should take 5 sec

    int zygotes[2];
    int trustlets[2];

    // for i in range(chain_len):
    //     zygotes.append(w.create_zygote("../libpal.so", "test4_manifest", "../libsysdb.so"))
    for (int i = 0; i < chain_len; i++) {
        zygotes[i] = create_zygote("../libpal.so", "test8_manifest", "../libsysdb.so");
    }

    // for i in range(chain_len):
    //     trustlets.append(zygotes[i].create_trustlet("./empty.py"))
    for (int i = 0; i < chain_len; i++) {
        trustlets[i] = create_trustlet(zygotes[i], "./empty.py");
    }

    // input_data = b"a" * (input_size - 1) + b"\00"
    char input_data[INPUT_SIZE];
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

        // prepare expected output
        char expected[INPUT_SIZE];
        memcpy(expected, input_data, input_size);
        // expected[2] += 1
        expected[2] += 1;
        // // expected[1] += i-1
        // expected[1] += i - 1;
        // expected = expected.decode('ascii').strip('\x00')
        // (in C, expected is already a string, strip null not needed for comparison)

        // #Setup Trustlets
        // for t in range(i - 1):
        //     trustlets[t].invoke_trustlet(b"a", 0)
        for (int t = 0; t < i - 1; t++) {
            // Transfer nodes (input->output)
            invoke_trustlet(trustlets[t], "a", 0);
        }
        // trustlets[i - 1].invoke_trustlet(b"x", 0)
        // End node (input->output->copy_to_caller)
        invoke_trustlet(trustlets[i - 1], "x", 0);

        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t start = ts.tv_sec * 1000000000ULL + ts.tv_nsec;

        // for _ in range(iterations):
        for (int iter = 0; iter < iterations; iter++) {
            // start = time.time_ns()

            // trustlets[0].invoke_trustlet(input_data,0)
            char* res = invoke_trustlet_bin(trustlets[1], input_data, input_size, input_size);
            debug printf("Input: \n");
            debug hexdump(input_data, input_size);
            debug printf("Output: \n");
            debug hexdump(res, input_size);

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

            // print(expected)
            debug printf("Expected: \n");
            debug printf("%s\n", expected);
            debug hexdump(expected, input_size);

            // assert res == expected
            assert(memcmp(res, expected, input_size) == 0);
        }

        clock_gettime(CLOCK_MONOTONIC, &ts);
        uint64_t end = ts.tv_sec * 1000000000ULL + ts.tv_nsec;
        printf("Packet rate: %.2f packets/sec\n", (double)iterations * 1e9 / (end - start));
    }

    return 0;
}
