import ctypes
import sys
import wallet
import time


with wallet.Wallet() as w:

    input_size = 16

    chain_len = 2
    chains = [2]

    iterations = 1

    zygotes = []
    trustlets = []

    for i in range(chain_len):
        zygotes.append(w.create_zygote("../libpal.so", "test1_manifest", "../libsysdb.so"))

    for i in range(chain_len):
        trustlets.append(zygotes[i].create_trustlet("./empty.py"))

    input_data = b"a" * (input_size - 1) + b"\00"
    for t in trustlets:
        t.invoke_trustlet(input_data, len(input_data))

    chained = 0

    for i in chains:
        #Create chains
        for c in range(chained,i - 1):
            trustlets[c].create_channel(trustlets[c+1])
        chained += i - chained - 1

        #Prepair input data
        input_data = b"b" * (input_size - 1) + b"\00"

        #Setup Trustlets
        for t in range(i - 1):
            #Transfer nodes (input->output)
            trustlets[t].invoke_trustlet(b"a", 0)
        #End node (input->output->copy_to_caller)
        trustlets[i - 1].invoke_trustlet(b"x", 0)

        for _ in range(iterations):
            start = time.time_ns()
            trustlets[0].invoke_trustlet(input_data,0)
            for t in range(1, i - 1):
                trustlets[t].invoke_trustlet(b"", 0)
            res = trustlets[i - 1].invoke_trustlet(b"", len(input_data))
            print(f"Output: {res}")
            end = time.time_ns()
            print((end - start) / 1e9)
            assert res == input_data.decode('ascii').strip('\x00')
