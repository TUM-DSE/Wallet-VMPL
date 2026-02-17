import ctypes
import sys
import wallet
import time

# like test3, but with simplified initialization

with wallet.Wallet() as w:

    input_size = 16

    chains = [1]
    chain_len = max(chains)

    iterations = 3 # invoke each chain multiple times

    zygotes = []
    trustlets = []

    for i in range(chain_len):
        zygotes.append(w.create_zygote("../libpal.so", "test13_manifest", "../libsysdb.so"))

    for i in range(chain_len):
        trustlets.append(zygotes[i].create_trustlet("./empty.py"))

    for i in chains:
        #Setup Trustlets
        for t in range(i - 1):
            #Transfer nodes (input->output)
            trustlets[t].invoke_trustlet(b"a", 0)
        #End node (input->output->copy_to_caller)
        trustlets[i - 1].invoke_trustlet(b"x", 0)

        #Prepair input data
        input_data = b"b" * (input_size - 1) + b"\00"

        for _ in range(iterations):
            start = time.time_ns()
            res = trustlets[0].invoke_trustlet(input_data, len(input_data))
            print(f"Output: {res}")
            end = time.time_ns()
            print((end - start) / 1e9)
            expected = bytearray(input_data)
            expected[2] += 1
            expected[1] += i-1
            expected = expected.decode('ascii').strip('\x00')
            print(expected)
            assert res == expected
