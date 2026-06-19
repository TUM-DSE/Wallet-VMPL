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
from util import safe_cast, deduplicate, strip_subnet_mask, is_kvm_version
from datetime import datetime
from subprocess import CalledProcessError
import traceback
import json
from os.path import dirname as path_dirname
from types import SimpleNamespace
import shlex


@dataclass
class StartupTest(AbstractBenchTest):
    system: str

    def test_infix(self):
        return f"startup_{self.system}"

    def estimated_runtime(self):
        return 20

    def run(self, host, repetition):
        host.exec(f'mkdir -p {path_dirname(self.output_filepath(repetition))} || true')
        if self.system == "vm":
            self.run_vm(host, repetition)
        elif self.system == "cvm":
            self.run_vm(host, repetition, confidential=True)
        # elif self.system == "kata":
        #     self.run_docker(host, "kata-qemu-slick", repetition)
        else:
            raise Exception(f"Unkown system {self.system}")
        pass

    def run_vm(self, host, repetition, confidential=False):
        cmd = [
            'sudo',
            # '/scratch/okelmann/Wallet-VMPL4/Benchmarks/CVM_eval/build/qemu-amd-sev-snp/bin/qemu-system-x86_64',
            f'{PROJECT_ROOT}/.nix-builds/qemu-coconut-igvm/bin/qemu-system-x86_64',

            # '-machine', 'q35,mem-merge=on',
            (f' -machine q35,confidential-guest-support=sev0,memory-backend=ram1' if confidential else f' -machine q35,mem-merge=on'), # not sure if this merging actually works (especially giving our memory scopes)
            (f' -object sev-snp-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,init-flags=4,igvm-file={PROJECT_ROOT}/svsm/bin/coconut-qemu.igvm' if confidential else ''),
            (f' -object memory-backend-memfd,id=ram1,size=15G,share=on' if confidential else ""),

            '-cpu', 'EPYC-v4,host-phys-bits=true',
            '-enable-kvm',
            '-smp', '1',
            '-m', '15G',
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

        output = "/tmp/bpftrace.log"
        host.exec(f"rm {output} || true")
        host.tmux_new("qemu-bpftrace", f"sudo bpftrace {PROJECT_ROOT}/boot_time_eval.bt | tee {output}")
        host.wait_for_success(f'grep "INITED" {output}', timeout=30)
        host.tmux_new(f"qemu", " ".join(cmd))
        # host.wait_for_success(f'grep "systemd init end" {output}', timeout=60)
        host.wait_for_success(f'grep "Trustlet Invocation End" {output}', timeout=60)
        host.tmux_kill("qemu")
        host.exec(f"cp {output} {self.output_filepath(repetition)}")

    def cleanup(self, host):
        host.tmux_kill("qemu")


def main(measurement):
    host, loadgen = measurement.hosts()
    tests : List[StartupTest] = []
    matrix = dict(
        system = [ "vm", "cvm" ],
        repetitions = [ 10 ],
        num_vms = [ 1 ],
    )
    if G.BRIEF:
        matrix = dict(
            system = [ "vm", "cvm" ],
            repetitions = [ 1 ],
            num_vms = [ 1 ],
        )
        matrix = measurement.apply_cmdline_overrides(matrix)
        tests = StartupTest.list_tests(matrix)
    matrix = measurement.apply_cmdline_overrides(matrix)
    tests = StartupTest.list_tests(matrix)
    StartupTest.estimate_time2(tests, [])

    if not is_kvm_version(host, of_system=True):
        warning("Incorrect KVM version (wallet). Reloading to system module. ")
        host.exec("sudo rmmod kvm_amd && sudo rmmod kvm")
        host.exec("sudo modprobe kvm_amd")

    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for _param_dict, a_tests in bench.multi_iterator_dict(bench_tests, [ "system", "num_vms" ]):
            assert len(a_tests) == 1 # we have looped through all variables now, right?
            test = a_tests[0]
            info(f"Running {test}")
            for repetition in range(test.repetitions):
                test.cleanup(host)
                test.run(host, repetition)
                test.cleanup(host)
            bench.done(test)


if __name__ == "__main__":
    measurement = Measurement(test_type=StartupTest)
    main(measurement)

