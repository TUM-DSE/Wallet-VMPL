import requests
import time
import sys

chains = [2, 4, 8, 16, 32]
addr = sys.argv[1]
t = sys.argv[2]
data = b"a" * 1024 * 16

iterations = 10

csv = open("results.csv","a")

#warmup
for _ in range(10):
    ret = requests.post(addr, data=data)

for chain_len in chains:
    for i in range(iterations):
        start = time.time_ns()
        for i in range(chain_len):
            ret = requests.post(addr, data=data)
            data = ret.content
        end = time.time_ns()
        csv.write(f"{t},{chain_len},{len(data)},{(end - start) / 1e9}\n")
