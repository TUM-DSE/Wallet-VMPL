import requests
import time
import sys
import secrets

sizes = [
    64,
    128,
    256,
    512,
    1024,
    4048,
    4096,
    8192,
    16384,
    32768,
    65546,
    131072,
    262144,
    1048576,
    2096152,
        ]
addr = sys.argv[1]
t = sys.argv[2]

data = b"a" * 1024

iterations = 10

csv = open("results.csv","a")

#warmup
for _ in range(10):
    ret = requests.post(addr, data=data)

for size_len in sizes:
    for i in range(iterations):
        data = secrets.token_bytes(size_len)
        ret_array = data
        start = time.time_ns()
        ret = requests.post(addr, data=data)
        ret_array = ret.content
        end = time.time_ns()
        csv.write(f"{t},{size_len},{(end - start) / 1e6}\n")
