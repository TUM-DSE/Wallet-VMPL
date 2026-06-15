from measure import Bench, AbstractBenchTest, Measurement, end_foreach
from conf import G
from typing import List
from logging import info, debug, error, warning
from dataclasses import dataclass, asdict
from server import Server, Host, Guest, LoadGen
from root import PROJECT_ROOT
from pandas import DataFrame
import pandas as pd
from os.path import join as path_join
import numpy as np
from enums import Interface
from time import sleep
import os
import getpass
from util import safe_cast, deduplicate, strip_subnet_mask
from datetime import datetime
from subprocess import CalledProcessError
import traceback
import json
from os.path import dirname as path_dirname
from types import SimpleNamespace
import shlex

INSTANCES = [ 1, 10, 20, 100, 200, 300, 400, 500, 600, 700 ]

@dataclass
class MemoryTest(AbstractBenchTest):
    system: str

    def test_infix(self):
        return f"mem_{self.system}_{self.num_vms}"

    def estimated_runtime(self):
        return 20

    def run(self, host, repetition):
        host.exec(f'mkdir -p {path_dirname(self.output_filepath(repetition))} || true')
        if self.system == "vm":
            self.run_vm(host, repetition)
        elif self.system == "cvm":
            self.run_vm(host, repetition, confidential=True)
        elif self.system == "kata":
            self.run_docker(host, "kata-qemu-slick", repetition)
        else:
            raise Exception(f"Unkown system {self.system}")
        pass


    def run_docker(self, host, runtime, repetition):
        batch = 10
        grace_boottime = 15

        dfs = []
        qemu_pids = []
        for i in range(self.num_vms):
            docker_cidfile = f"/tmp/docker-cid-{i}"
            # docker_run_log = f"/tmp/docker-run-log-{i}"
            # host.exec(f"sudo rm {docker_run_log} || true")
            cid = host.exec(f'docker run --rm --runtime {runtime} -d ubuntu:24.04 sleep 999').strip()
            host.exec(f"echo {cid} > {docker_cidfile}")
            # host.wait_for_success(f"grep ok {docker_run_log}", timeout=30)
            # cid = host.exec(f"cat {docker_cidfile}").strip()
            # memory = host.exec(f"cat /sys/fs/cgroup/system.slice:docker:{cid}/memory.peak") # only the container, not the qemu
            qemu_pid = host.exec(f"pgrep -f 'qemu.*{cid}'").strip()
            qemu_pids += [ qemu_pid ]

            if (i % batch) == 0 or i+1 in INSTANCES: # give each batch ample startup time
                print(f"Wait for VM {i} to come up")
                sleep(grace_boottime)

            if i+1 in INSTANCES:
                # collect measurement
                mem_usages = []
                for j in range(i+1):
                    resident_pages = int(host.exec(f"cat /proc/{qemu_pids[j]}/statm").strip().split(" ")[1])
                    memory = resident_pages * 4096
                    mem_usages += [ memory ]
                print(mem_usages)
                data = [{
                    **asdict(self), # put selfs member variables and values into this dict
                    "repetition": repetition,
                    "instances": i+1,
                    "per_vm_stddev": np.std(mem_usages),
                    "bytes": np.sum(mem_usages),
                }]
                df = DataFrame(data=data)
                print(df.to_string())
                dfs += [ df ]

        df = pd.concat(dfs)
        print(df)
        pd.concat(dfs).to_csv(self.output_filepath(repetition), index=False)

    def run_vm(self, host, repetition, confidential=False):
        batch = 10
        grace_boottime = 30

        dfs = []
        for i in range(self.num_vms):
            host.exec(f"sudo mkdir /sys/fs/cgroup/vm_scale_{i}")
            cmd = [
                'sudo', 'cgexec', '--sticky', '-g', f'memory:vm_scale_{i}',
                # '/scratch/okelmann/Wallet-VMPL4/Benchmarks/CVM_eval/build/qemu-amd-sev-snp/bin/qemu-system-x86_64',
                f'{PROJECT_ROOT}/.nix-builds/qemu-coconut-igvm/bin/qemu-system-x86_64',

                # '-machine', 'q35,mem-merge=on',
                (f' -machine q35,confidential-guest-support=sev0' if confidential else f' -machine q35,mem-merge=on'), # not sure if this merging actually works (especially giving our memory scopes)
                (f' -object sev-snp-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,init-flags=4,igvm-file={PROJECT_ROOT}/svsm/bin/coconut-qemu.igvm' if confidential else ''),

                '-cpu', 'host',
                '-enable-kvm',
                '-smp', '1',
                '-m', '0.5G',
	            f'-drive file={PROJECT_ROOT}/guest.qcow2,if=none,id=disk0,format=qcow2,snapshot=on',
	            '-device virtio-scsi-pci,id=scsi0,disable-legacy=on,iommu_platform=on',
	            '-device scsi-hd,drive=disk0,bootindex=0',
                # '-kernel', '/scratch/okelmann/Wallet-VMPL4/Benchmarks/CVM_eval/../linux/arch/x86/boot/bzImage',
                # '-append', 'root=/dev/vda console=hvc0 ',
                # '-drive', 'format=qcow2,file.driver=file,file.filename=../CVM_eval/build/image/guest-fs-sebs.qcow2,if=virtio,snapshot=on',
                # '-virtfs', 'local,path=/scratch/okelmann/Wallet-VMPL4/Benchmarks/CVM_eval,security_model=none,mount_tag=share',
                # '-drive', 'if=pflash,format=raw,unit=0,file=/scratch/okelmann/Wallet-VMPL4/Benchmarks/CVM_eval/build/ovmf-amd-sev-snp-fd/FV/OVMF.fd,readonly=on',
                '-nographic',
                # '-serial', 'null',
                # '-device', 'virtio-serial',
                # '-chardev', 'stdio,mux=on,id=char0,signal=off',
                # '-mon', 'chardev=char0,mode=readline',
                # '-device', 'virtconsole,chardev=char0,id=vc0,nr=0',
	            f'-virtfs local,path={PROJECT_ROOT}/module/,mount_tag=mo,security_model=passthrough',
	            f'-virtfs local,path={PROJECT_ROOT}/Benchmarks/,mount_tag=benchmarks,security_model=passthrough',
	            f'-virtfs local,path={PROJECT_ROOT}/gramine-svsm/,mount_tag=gramine,security_model=passthrough',
	            f'-virtfs local,path={PROJECT_ROOT}/../,mount_tag=home,security_model=passthrough',
	            '-virtfs local,path=/nix/store/,mount_tag=nixstore,security_model=passthrough',
            ]
            host.tmux_new(f"qemu-{i}", " ".join(cmd))

            if (i % batch) == 0 or i+1 in INSTANCES: # give each batch ample startup time
                print(f"Wait for {'CVM' if confidential else 'VM'} {i} to come up")
                sleep(grace_boottime)

            if i+1 in INSTANCES:
                # collect measurement
                mem_usages = []
                for j in range(i+1):
                    mem_usages += [ int(host.exec(f"cat /sys/fs/cgroup/vm_scale_{j}/memory.peak")) ]
                print(mem_usages)
                data = [{
                    **asdict(self), # put selfs member variables and values into this dict
                    "repetition": repetition,
                    "instances": i+1,
                    "per_vm_stddev": np.std(mem_usages),
                    "bytes": np.sum(mem_usages),
                }]
                df = DataFrame(data=data)
                print(df.to_string())
                dfs += [ df ]

        df = pd.concat(dfs)
        print(df)
        pd.concat(dfs).to_csv(self.output_filepath(repetition), index=False)


    def cleanup(self, host):
        # docker
        host.exec('cat /tmp/docker-cid-* | xargs -I {} sh -c "docker kill {} || true"')
        host.exec("sudo rm /tmp/docker-cid-* || true")

        # vm
        host.tmux_kill("qemu")
        sleep(2)
        host.exec("sudo rmdir /sys/fs/cgroup/vm_scale* || true")

def main(measurement):
    host, loadgen = measurement.hosts()
    tests : List[MemoryTest] = []
    matrix = dict(
        system = [ "vm", "cvm", "kata" ],
        num_vms = [ 20 ],
        repetitions = [ 1 ],
    )
    matrix = measurement.apply_cmdline_overrides(matrix)
    tests = MemoryTest.list_tests(matrix)

    for test in tests:
        for repetition in range(test.repetitions):
            test.cleanup(host)
            repetition = 0
            test.run(host, repetition)
            test.cleanup(host)

if __name__ == "__main__":
    measurement = Measurement(test_type=MemoryTest)
    main(measurement)
