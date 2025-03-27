#!/usr/bin/env python3

import re
import numpy as np
import os

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

        elif "Monitor: Start" in line:
            monitor_start = ti(line)
        elif "Monitor: Load Guest" in line:
            monitor_guest = ti(line)
        elif ": 50" in line:
            ovmf_start = ti(line)
        elif ": 52" in line:
            ovmf_end = ti(line)
        elif "Linux: systemd" in line:
            guest_startup = ti(line)
        elif "101 Runtime: Monitor connection" in line:
            runtime_con_start = ti(line)
        elif "102 Runtime: Monitor connection" in line:
            runtime_con_end = ti(line)
        elif "103 Runtime: Zygote Creation" in line:
            runtime_zygote_start = ti(line)
        elif "104 Runtime: Zygote Creation End" in line:
            runtime_zygote_end = ti(line)
        elif "105 Runtime: Trustlet Creation" in line:
            runtime_trustlet_start = ti(line)
        elif "106 Runtime: Trustlet Creation End" in line:
            runtime_trustlet_end = ti(line)
        elif "107 Runtime: Trustlet Invocation" in line:
            runtime_invoke = ti(line)
        elif "110 Runtime: In Python environment" in line:
            runtime_python_call = ti(line)

    #print(runtime_con_end)
    qemu_delay = monitor_start - qemu_start
    monitor_delay = monitor_guest - monitor_start
    ovmf_delay = ovmf_end - ovmf_start
    linux_delay = guest_startup - ovmf_end
    runtime_startup = runtime_con_end - guest_startup
    runtime_zygote = runtime_zygote_end - runtime_con_end
    runtime_trustlet = runtime_trustlet_end - runtime_zygote_end
    runtime_invoke = runtime_python_call - runtime_trustlet_end

    return qemu_delay, monitor_delay, ovmf_delay, linux_delay, runtime_startup, runtime_zygote,\
        runtime_trustlet, runtime_invoke



if __name__ == "__main__":

    results = []
    directory = os.fsencode("result/")
    for file in os.listdir(directory):
        #print(file)
        filename = os.fsdecode(file)
        if filename.endswith(".txt"):
            results.append(parse_boottime("result/" +filename))

    #print(results)


    vm_avg = np.mean(results, axis=0)
    vm_std = np.std(results, axis=0)

    MAPPING = ["QEMU", "Monitor", "OVMF", "Linux", "Runtime", "Zygote", "Trustlet", "Invoke"]

    print("Wallet stats:")
    for i in range(len(MAPPING)):
        print(f"{MAPPING[i]}: {vm_avg[i]/1000000} ms, std: {vm_std[i]/1000000} ms")

    res = "VM,Type,QEMU,Monitor,Linux/OVMF,Runtime,Zygote,Trustlet,Invoke\n"
    res += f"Wallet,Cold,{vm_avg[0]/1000000},{vm_avg[1]/1000000},{vm_avg[2]/1000000},{vm_avg[3]/1000000},{vm_avg[4]/1000000},{vm_avg[5]/1000000},{vm_avg[6]/1000000}\n"
    res += f"Wallet,Warm 1,0,0,0,0,{vm_avg[4]/1000000},{vm_avg[5]/1000000},{vm_avg[6]/1000000}\n"
    res += f"Wallet,Warm 2,0,0,0,0,0,{vm_avg[5]/1000000},{vm_avg[6]/1000000}"

    with open("result.csv","w") as f:
        f.write(res)
