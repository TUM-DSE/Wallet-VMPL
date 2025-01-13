#!/usr/bin/env python3

import re
import numpy as np
import os

def parse(filename):
    with open(filename, "r") as f:
        text = f.readlines()

    def ti(line):
        return int(line.split(":")[0])


    res = []

    file_size = int(filename.split("res-")[1].split(".txt")[0])

    current_start = False

    for line in text:

        if "COPY Start" in line:
            if current_start:
                print("COULD not parse")
                exit(0)
            start = ti(line)
            current_start = True
        elif "DONE" in line:
            if not current_start:
                print("COULD not parse")
                exit(0)
            end = ti(line)
            current_start = False
            res.append( (end - start)/ 10e6)

    res = np.array(res)

    return (file_size, res.mean(), res.std())

if __name__ == "__main__":

    results = []
    directory = os.fsencode("result/")
    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        if filename.endswith(".txt"):
            results.append(parse("result/" +filename))

    print(results)
    results.sort(key=lambda x: x[0])

    with open("res.csv", "w") as f:
        f.write("size,mean,std\n")
        for r in results:
            f.write(f"{r[0]},{r[1]},{r[2]}\n")
