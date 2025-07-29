#!/usr/bin/env python3

import re
import numpy as np
import os

def parse_boottime(filename):
    with open(filename, "r") as f:
        text = f.readlines()
    f = [float(x) for x in text]
    return f

if __name__ == "__main__":

    results = parse_boottime("result")



    vm_avg = np.mean(results, axis=0)
    vm_std = np.std(results, axis=0)

    with open("result.txt", "w") as f:
        f.write("Native:\n")
        f.write(f"Total: {vm_avg} ms, std: {vm_std} ms\n")
