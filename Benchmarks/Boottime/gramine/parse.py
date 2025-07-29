#!/usr/bin/env python3

import re
import numpy as np
import os

def parse_boottime(filename):
    with open(filename, "r") as f:
        text = f.readlines()

    start_time = int(text[0]) / 1e6
    second_time = int(text[1].split("Time: ")[1]) / 1e3
    end_time = int(text[2]) / 1e6

    gramine = second_time - start_time
    invoke = end_time -second_time

    return gramine,invoke

if __name__ == "__main__":

    results = []
    directory = os.fsencode("result/")
    for file in os.listdir(directory):
        #print(file)
        filename = os.fsdecode(file)
        if filename.endswith(".txt"):
            results.append(parse_boottime("result/" +filename))

    print(results)

    #print(results)


    vm_avg = np.mean(results, axis=0)
    vm_std = np.std(results, axis=0)
    print("\n")
    print(vm_avg, vm_std)

    with open("result.txt", "w") as f:
        f.write("Gramine stats:\n")
        f.write(f"Runtime: {vm_avg[0]} ms, std: {vm_std[0]} ms\n")
        f.write(f"Invoke: {vm_avg[1]} ms, std: {vm_std[1]} ms\n")
