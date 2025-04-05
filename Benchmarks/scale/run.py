#!/usr/bin/env python3

import sys
import os
from tempfile import TemporaryDirectory
from pathlib import Path
import subprocess
import time

sys.path.append("../CVM_eval/")
sys.path.append("../CVM_eval/tasks")

from tasks.vm import (
    VMResource,
    get_vm_resource,
    get_snp_direct_qemu_cmd,
    get_amd_vm_direct_qemu_cmd,
)
from tasks.qemu import spawn_qemu
from tasks.config import SSH_PORT

from multiprocessing import Process, Lock, Array

out = open("result.csv", "w")
vm_type = "vm"
mem = 0.5

import docker


def spawn_container(i, arr, l):
    client = docker.from_env()
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
    l.acquire()
    l.release()
    container.reload()
    if not "running" in container.status:
        arr[i] = 0
        container.stop()
        return

    cid = container.id
    with open(f"/sys/fs/cgroup/system.slice:docker:{cid}/memory.peak") as f:
        peak_memory = int(f.read())
    arr[i] = peak_memory

    container.stop()


def run_kata(n=1):
    lock = Lock()
    lock.acquire()
    result_array = Array("i", range(n))
    process_list = []
    for i in range(n):
        p = Process(target=spawn_container, args=(i, result_array, lock))
        process_list.append(p)
    print(f"Starting {n} containers")
    for p in process_list:
        p.start()
    time.sleep(20)
    lock.release()

    for p in process_list:
        p.join()

    for e in result_array[:]:
        if e == 0:
            print("Kata failed")
            exit(-1)
    out.write(f"kata,{n},0.5,{sum(result_array[:])}\n")
    out.flush()
    print("Memory: ", sum(result_array[:]))


def spawn_qemu(c, l, result_array, num):
    with TemporaryDirectory() as tempdir:
        qmp_socket = Path(tempdir).joinpath("qmp.sock")
        cmd = ["sudo", "cgexec", "--sticky", "-g", "memory:vm_scale"]
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

        p.kill()
        time.sleep(60)
        if p.poll():
            result_array[num] = True
            return
        result_array[num] = False


def spawn_qemu_parallel(config, n=1):
    # Create Cgroup
    subprocess.run(["sudo", "rmdir", "/sys/fs/cgroup/vm_scale"])
    subprocess.run(["sudo", "mkdir", "/sys/fs/cgroup/vm_scale"])

    process_list = []
    lock = Lock()
    lock.acquire()
    result_array = Array("i", range(n))
    for i in range(n):
        p = Process(target=spawn_qemu, args=(config, lock, result_array, i))
        process_list.append(p)

    counter = 0
    for p in process_list:
        counter += 1
        # if(counter == 20):
        #    time.sleep(10)
        #    counter = 0
        p.start()

    # Wait for all VMs to boot
    # if(n > 100):
    #    time.sleep(30 * (n/100))
    time.sleep(120)
    time.sleep(n)

    with open("/sys/fs/cgroup/vm_scale/memory.peak", "r") as f:
        peak_memory = int(f.read())
    print("Memory: ", peak_memory)
    out.write(f"{vm_type},{n},{mem},{peak_memory}\n")
    out.flush()
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

    cmd = [x for x in cmd if not "net0" in x]
    cmd.remove("-netdev")
    cmd.remove("-device")

    print(" ".join(cmd))
    extra_args = ["sudo", "cgexec", "--sticky", "-g", "memory:vm_bench"]
    for i in it:
        a = spawn_qemu_parallel(cmd, i)
        if not a:
            return False
    return True
    # a.__enter__()

    print(r)


for m in [0.5]:
    mem = m
    for i in [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99]:
        run_kata(i)

    continue
    if not run_vm("amd", m, [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99]):
        print("Failed to get data")
        break

out.close()
