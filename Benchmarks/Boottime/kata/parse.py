#!/usr/bin/env python3

import re
import numpy as np
import os
import sys
from dateutil import parser

def parse_boottime(filename):
    with open(filename, "r") as f:
        text = f.readlines()

    def ti(line):
        return int(line.split(":")[0])


    for line in text:
        if "QEMU: main" in line:
            if "qemu_start" in locals():
                continue
            qemu_start = ti(line)
        elif ": 50" in line:
            bios_start = ti(line)
        elif ": 52" in line:
            bios_end = ti(line)
    print(filename)
    return qemu_start, bios_start, bios_end

def parse_start(filename):
    with open(filename,"r") as f:
        text = f.readlines()

    for line in text:
        if "Start" in line:
            start = int(line.split(": ")[1])
        if "End" in line:
            end = int(line.split(": ")[1])

    return start,end

def parse_log(filename):
    with open(filename, "r") as f:
        log = f.readlines()

    def get_time(l):
        l = l.split("time=\"")[1]
        l = l.split("Z\" level")[0]
        tt = l.split(".")
        t = int(parser.isoparse(tt[0]).timestamp()) * 1000000000
        t2 = int(tt[1])
        return t + t2

    """
    New client -> agent started
    Agent started in the sandbox -> agent started sandbox
    management server started -> server started in sandbox
    Sandbox is started
    """

    c = 0

    for line in reversed(log):
        if c == 2:
            break
        if "Agent started in the sandbox" in line:
            agent_time = get_time(line)
            c += 1
        if "kata management inited" in line:
            agent_time_end = get_time(line)
            c+= 1
    
    print(filename)

    return agent_time, agent_time_end


def parse(i):
    early_init = parse_boottime(f"result/res-{i}.txt")
    start_end = parse_start(f"result/se-{i}.txt")
    log = parse_log(f"result/log-{i}.txt")
    t = {
        "Early runtime": (early_init[0] - start_end[0]) / 1e6,
        "QEMU": (early_init[1] - early_init[0]) / 1e6,
        "OVMF": (early_init[2] - early_init[1]) / 1e6,
        "Linux": (log[0] - early_init[2]) / 1e6,
        "Runtime": (start_end[1] - log[1]) / 1e6,

    }

    return t

if __name__ == "__main__":

    results = []
    #for file in os.listdir(directory):
        #print(file)
    #    filename = os.fsdecode(file)
    #    if filename.endswith(".txt") and filename.contains("res-"):
    #        results.append(parse_boottime("result/" +filename))
    iters = int(sys.argv[1])

    for i in range(iters):
        results.append(parse(i))

    res = {
        "Early runtime": [],
        "QEMU": [],
        "OVMF": [],
        "Linux": [],
        "Runtime": [],


    }
    mappings = ["Early runtime", "QEMU", "OVMF", "Linux", "Runtime"]
    for r in results:
        for m in mappings:
            res[m].append(r[m])

    s = []

    for i in range(iters):
        s.append(res["Runtime"][i])
        res["Runtime"][i] += res["Early runtime"][i]
    #print(f"Inner runtime: {s / iters}")
    s_std = np.std(s)
    s = np.mean(s)
    print(f"Inner runtime: {s} std: {s_std}")

    mappings = [ "QEMU", "OVMF", "Linux", "Runtime"]
    for m in mappings:
        mean = np.mean(res[m])
        std = np.std(res[m])
        res[m] = (mean,std)

    with open("result.txt", "w") as f:
        f.write("Kata Containers:\n")
        for m in mappings:
            f.write(f"{m}: {res[m][0]} ms, std: {res[m][1]} ms\n")
