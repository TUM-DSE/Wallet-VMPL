#!/usr/bin/env python3

import sys
import os
from tempfile import TemporaryDirectory
from pathlib import Path
import subprocess
import time
import resource

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


def spawn_qemu(c, l, result_array, num):
    with TemporaryDirectory() as tempdir:
        qmp_socket = Path(tempdir).joinpath("qmp.sock")
        print("Starting VM: ", num)
        cmd = ["sudo", "cgexec", "--sticky", "-g", f"memory:vm_scale_{num}"]
        qmp_command = [
            "-qmp",
            f"unix:{str(qmp_socket)},server,nowait",
        ]
        cmd += c
        # print(cmd)

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        l.acquire()
        l.release()
        if p.poll():
            result_array[num] = -1
            print("STDOUT:", p.stdout.read())
            print("STDERR:", p.stderr.read())
            return
        print(f"Stopping {num}")
        p.kill()
        time.sleep(60)
        if p.poll():
            result_array[num] = True
            return

        print("STDOUT:", p.stdout.read())
        print("STDERR:", p.stderr.read())
        result_array[num] = False


def spawn_qemu_parallel(config, n=[1]):
    max_value = n[-1]
    # Create Cgroups
    for i in range(max_value):
        subprocess.run(["sudo", "rmdir", f"/sys/fs/cgroup/vm_scale_{i}"])
        subprocess.run(["sudo", "mkdir", f"/sys/fs/cgroup/vm_scale_{i}"])

    process_list = []
    lock = Lock()
    lock.acquire()
    result_array = Array("i", range(max_value))
    offset = 0
    start = n[0]
    exec_list = []
    for i in range(len(n)):
        if i == 0:
            exec_list.append(n[i])
        else:
            exec_list.append(n[i] - n[i - 1])
    print(f"VM cycles: {exec_list}")
    for vms in exec_list:
        if offset != 0:
            print(f"Starting {start} additional VMs")
        else:
            print(f"Starting {vms} VMs")

        for i in range(offset, offset + vms, 1):
            p = Process(target=spawn_qemu, args=(config, lock, result_array, i))
            process_list.append(p)
            print(i, i + offset)
            counter = 0
        for p in process_list[offset:]:
            counter += 1
            p.start()
            if counter > 50:
                time.sleep(15)
                counter = 0

        time.sleep(60 + vms / 100)

        peak_memory = 0
        for i in range(offset + vms):
            with open(f"/sys/fs/cgroup/vm_scale_{i}/memory.peak", "r") as f:
                peak_memory += int(f.read())
        print(f"Memory({vms}): ", peak_memory)
        shared = get_shared()
        out.write(f"{vm_type},{vms + offset},{mem},{peak_memory},{shared}\n")
        out.flush()
        offset += vms
    # Unlock to stop all VMs
    lock.release()
    for p in process_list:
        p.join()

    print(result_array[:])
    if sum(result_array[:]) != n:
        print("Some VMs failed to start")
        return False
    else:
        print("No VM did fail")
        return True


def run_vm(vm="amd", mem=2, it=[]):
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
    
    print("COMMAND: ", " ".join(cmd))

    cmd = [x for x in cmd if not "net0" in x]
    cmd.remove("-netdev")
    cmd.remove("-device")
    for i in range(len(cmd)):
        if "q35" in cmd[i]:
            cc = cmd[i]
            if len(cc.split("q35")[1]) == 0:
                cmd[i] = "q35,mem-merge=on"
            else:
                cmd[i] = "q35,mem-merge=on" + cc.split("q35")[1]

    print("COMMAND: ", " ".join(cmd))

    a = spawn_qemu_parallel(cmd, it)
    if not a:
        return False
    return True
    # a.__enter__()

    print(r)


runtime = sys.argv[1]
match runtime:
    case "vm":
        vm_type = "vm"
        run_vm("amd", 0.5, [1, 100, 200, 300, 400, 500, 600, 700])
    case "cvm":
        vm_type = "cvm"
        run_vm("snp", 0.5, [1, 100, 200, 300, 400, 500])
    case "kata":
        run_kata([1, 100, 200, 300, 400, 500, 600, 700])
# run_kata(n)
# run_vm("amd", 0.5, [100,200,300,400,500,600,700])
# run_vm("amd",0.5, [1,2])
out.close()
