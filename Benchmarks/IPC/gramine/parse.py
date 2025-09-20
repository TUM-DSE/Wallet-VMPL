#!/usr/bin/env python3

import re
import numpy as np
import os
import sys

def parse(filename):
    with open(filename, "r") as f:
        text = f.readlines()

    res = []

    file_size = int(filename.lstrip("res-").rstrip(".txt").split("-")[-1])

    for line in text[1:]:
        res.append(int(line.strip()) / 1000)

    res = np.array(res)

    return (file_size, res.mean(), res.std())

if __name__ == "__main__":

    # e.g. python3 ../parse.py native pipe

    results = []
    directory = os.fsencode(f"result_{sys.argv[1]}/")
    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        if filename.endswith(".txt"):
            if len(sys.argv) >= 3:
                if filename.split("res-")[1].split("-")[0] == sys.argv[2]:
                    results.append(parse(f"result_{sys.argv[1]}/" +filename))
                else:
                    pass # skip other files
            else:
                results.append(parse(f"result_{sys.argv[1]}/" +filename))

    print(results)
    results.sort(key=lambda x: x[0])

    name = f"res_{sys.argv[1]}_{sys.argv[2]}.csv" if len(sys.argv) >= 3 else f"res_{sys.argv[1]}.csv"
    with open(name, "w") as f:
        f.write("size,mean,std\n")
        for r in results:
            f.write(f"{r[0]},{r[1]},{r[2]}\n")
