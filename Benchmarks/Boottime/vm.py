#!/usr/bin/env python3

import sys
import os
from tempfile import TemporaryDirectory
from pathlib import Path
import subprocess
import time
import resource
import numpy as np

sys.path.append("../CVM_eval/")
sys.path.append("../CVM_eval/tasks")

# resource.setrlimit(resource.RLIMIT_NPROC, (163840,163840))
# print(f"Set limit: {resource.getrlimit(resource.RLIMIT_NPROC)}")
from tasks.vm import (
    VMResource,
    get_vm_resource,
    get_snp_direct_qemu_cmd,
    get_amd_vm_direct_qemu_cmd,
)
from tasks.qemu import spawn_qemu
from tasks.config import SSH_PORT

from multiprocessing import Process, Lock, Array, Value


result_file = Path("result.csv")
if not result_file.is_file():
    out = open("result.csv", "w")
    out.write("type,instances,assigned_memory,memory_usage,shared_pages\n")
    out.flush()
else:
    out = open("result.csv", "a")

vm_type = "vm"
mem = 0.5

import docker


def get_shared():
    with open("/sys/kernel/mm/ksm/pages_shared", "r") as f:
        return int(f.read())


def spawn_containers(i, arr, l, value):
    client = docker.from_env()
    containers = []
    env = {
        "CONTAINER_GID": str(os.getgid()),
        "CONTAINER_UID": str(os.getuid()),
        "CONTAINER_USER": "docker_user",
    }
    container = client.containers.run(
        runtime="kata-qemu",
        image="sebs:run.kata_qemu.python.3.11",
        command=f"/bin/bash /sebs/run_server.sh 9003",
        environment=env,
        remove=True,
        stdout=True,
        stderr=True,
        detach=True,
    )
    print(f"Started container {i}")
    time.sleep(10)
    container.reload()

    cid = container.id

    if "running" in container.status:
        with open(f"/sys/fs/cgroup/system.slice:docker:{cid}/memory.peak") as f:
            peak_memory = int(f.read())
        arr[i] = peak_memory
    l.acquire()
    l.release()
    container.reload()

    if not "running" in container.status:
        arr[i] = 0
        container.stop()
        return

    with open(f"/sys/fs/cgroup/system.slice:docker:{cid}/memory.peak") as f:
        peak_memory = int(f.read())
    arr[i] = peak_memory

    container.stop()
    client.close()


def run_kata(n=[1]):
    lock = Lock()
    lock.acquire()
    result_array = Array("i", range(n[-1]))
    mem_total = Value("i", 0)
    process_list = []
    exec_list = []
    for i in range(len(n)):
        if i == 0:
            exec_list.append(n[i])
        else:
            exec_list.append(n[i] - n[i - 1])
    print(f"VM cycles: {exec_list}")
    offset = 0
    for vms in exec_list:
        if offset != 0:
            print(f"Starting {vms} additional VMs")
        else:
            print(f"Starting {vms} VMs")

        for i in range(offset, offset + vms, 1):
            p = Process(
                target=spawn_containers, args=(i, result_array, lock, mem_total)
            )
            process_list.append(p)

        for p in process_list[offset:]:
            p.start()

        time.sleep(20)
        time.sleep(vms / 4)

        used_memory = sum(result_array[0 : (vms + offset)])
        shared = get_shared()
        out.write(f"kata,{vms + offset},0.5,{used_memory},{shared}\n")
        out.flush()
        offset += vms

    lock.release()

    for p in process_list:
        p.join()
    time.sleep(20)
    for e in result_array[:]:
        if e == 0:
            print("Kata failed")
            exit(-1)
    print("All Kata VMs were created correctly")
    print("Memory: ", sum(result_array[:]))

def parse_result(start_time, path):
    with open(path, "r") as f:
        res = f.readlines()
    
    start = 0
    ovmf = 0
    linux = 0
    linux_end = 0
    runtime = 0
    for l in res:
        if "QEMU: main" in l:
            start = int(l.split(":")[0].replace("\0", ""))
            break
    for l in res:
        if "0 OVMF:" in l:
            ovmf = int(l.split(":")[0])
            break
    for l in res:
        if "230 Linux:" in l:
            linux = int(l.split(":")[0])
            break
    for l in res:
        if "231 Linux:" in l:
            linux_end = int(l.split(":")[0])
            break
    for l in res:
        if "240 Linux:" in l:
            runtime = int(l.split(":")[0])
            break
    print(ovmf-start, linux-ovmf, linux_end-linux,runtime-linux_end)
    



def spawn_qemu(cmd, path):
    with TemporaryDirectory() as tempdir:
        log = open(path, "w")
        #bpf = subprocess.Popen(["sudo",
        #    "bpftrace", "boot_time_eval.bt"],
         #                      stdout=log, stderr=log, cwd="../CVM_eval/benchmarks/boottime")
        #print("Starting VM")
        start_time = time.time_ns()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(30)
        if p.poll():
            print("STDOUT:", p.stdout.read())
            print("STDERR:", p.stderr.read())
            return
        #print("Stopping VM")
        p.kill()
        #bpf.kill()
        log.close()
        time.sleep(10)
        parse_result(start_time, path)
        if p.poll():
            return
        else:
            print("Failed to stop VM")
            return

def run_vm(vm="amd", mem=2, path="/tmp/testout"):
    r = get_vm_resource(vm, "small")
    r.memory = mem

    c = {
        "image": "../CVM_eval/build/image/guest-fs-sebs.qcow2",
        "ssh_port": None,
        "boot_prealloc": False,
    }

    if vm == "amd":
        cmd = get_amd_vm_direct_qemu_cmd(r, c)
    else:
        cmd = get_snp_direct_qemu_cmd(r, c)
    
    #print("COMMAND: ", " ".join(cmd))

    cmd = [x for x in cmd if not "net0" in x]
    cmd.remove("-netdev")
    cmd.remove("-device")

    #print("COMMAND: ", " ".join(cmd))

    a = spawn_qemu(cmd,path)
    return
    if not a:
        return False
    return True
    # a.__enter__()

    print(r)


def parse_end_result(path, res_path, t):
    with open(path, "r") as f:
        res = f.readlines()

    res = [x.replace("\n","") for x in res]
    qemu = []
    ovmf = []
    linux = []
    runtime = []
    for r in res:
        s = r.split(" ")
        qemu.append(int(s[0]))
        ovmf.append(int(s[1]))
        linux.append(int(s[2]))
        runtime.append(int(s[3]))

    with open(res_path, "w") as file:
        file.write(f"{t}:\n")
        file.write(f"QEMU: {np.average(qemu) / 1e6} ms, std: {np.std(qemu) / 1e6} ms\n")
        file.write(f"OVMF: {np.average(ovmf) / 1e6} ms, std: {np.std(ovmf) / 1e6} ms\n")
        file.write(f"Linux: {np.average(linux) / 1e6} ms, std: {np.std(linux) / 1e6} ms\n")
        file.write(f"Runtime: {np.average(runtime) / 1e6} ms, std: {np.std(runtime) / 1e6} ms\n")


runtime = sys.argv[1]
match runtime:
    case "vm":
        vm_type = "vm"
        run_vm("amd", 32, "/tmp/vm_trace")
    case "cvm":
        vm_type = "cvm"
        run_vm("snp", 32, "/tmp/cvm_trace")
    case "cvm_parse":
        parse_end_result("./cvm.txt", "cvm_result.txt","CVM")
    case "vm_parse":
        parse_end_result("./vm.txt", "vm_result.txt","VM")
out.close()
