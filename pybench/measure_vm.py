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

TARGET = {
    "polling": "build/polling_test-shared",
    "procedural": "build/procedural_test-shared",
    "noiomgr": "build/noiomgr_test-shared"
}

LLC_SIZE = 512*1024*1024 # 512 MB last level cache

@dataclass
class UserspaceTest(AbstractBenchTest):

    batchsize: int
    workload: int
    chaining: int
    system: str
    pktsize: int

    def test_infix(self):
        return f"userspace_{self.system}_b{self.batchsize}_{self.workload}ns_c{self.chaining}_{self.pktsize}b"

    def estimated_runtime(self) -> float:
        return 5

    def compile(self, server: Server):
        cflags = " ".join([
            f"-DBURST_SIZE={self.batchsize}",
            f"-DPER_VNFLET_WORKLOAD_NS={self.workload}",
            f"-DCHAINING={self.chaining}",
            f"-DLLC_SIZE={LLC_SIZE}",
            f"-DPACKET_SIZE={self.pktsize}",
        ])
        server.exec(f"make -C {PROJECT_ROOT} {TARGET[self.system]} -B CFLAGS=\"{cflags}\"")
        pass

    def run(self, server: Server, repetition: int):
        remote_output_file = "/tmp/output.log"
        local_output_file = self.output_filepath(repetition)
        server.exec(f"sudo {PROJECT_ROOT}/{TARGET[self.system]} -l 0,6-12 > {remote_output_file} 2>&1")
        server.copy_from(remote_output_file, local_output_file)
        pass

    def parse_results(self, repetition):
        local_output_file = self.output_filepath(repetition)
        with open(local_output_file, 'r') as f:
            lines = f.readlines()
        lines = [ line for line in lines if "System throughput:" in line]
        assert len(lines) == 1 # Our test prints this line only once
        line = lines[0]
        value = line.split("System throughput: ")[1].split("Mops/s")[0].strip()
        value = float(value)

        return DataFrame(data=[{
            **asdict(self),
            "repetition": repetition,
            "Mpps": value
        }])




def main(measurement: Measurement, plan_only: bool = False) -> None:
    global LLC_SIZE
    host, loadgen = measurement.hosts()
    test_matrix = dict(
        repetitions=[1],
        batchsize = [1, 32],
        workload = [ int(i) for i in np.linspace(0, 50, 20) ] + [ int(i) for i in np.linspace(20, 2000, 20) ],
        chaining = [3],
        system = [ "polling", "procedural", "noiomgr" ],
        pktsize = [ 64, 1500 ],

        # legacy args
        num_vms = [0],
    )
    if G.BRIEF:
        LLC_SIZE = 512*1024 # reduce memory consumption for laptops
        test_matrix = dict(
            repetitions=[1],
            batchsize = [1], # , 32],
            workload = [ 0 ], # , 100 ],
            chaining = [3],
            system = [ "polling" ], #, "procedural", "noiomgr" ],
            pktsize = [ 64 ],

            # legacy args
            num_vms = [0],
        )

    tests : List[UserspaceTest] = []
    tests = UserspaceTest.list_tests(test_matrix)
    UserspaceTest.estimate_time2(tests, [])

    if plan_only:
        return

    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for [repetitions, batchsize, workload, chaining, system, pktsize], a_tests in bench.multi_iterator(bench_tests, ["repetitions", "batchsize", "workload", "chaining", "system", "pktsize"]):
            assert len(a_tests) == 1 # we have looped through all variables now, right?
            test = a_tests[0]
            info(f"Running {test}")
            host.stop_pktgen_vhost()
            host.start_pktgen_vhost()
            sleep(1) # wait and pray for pktgen
            with measurement.virtual_machine(Interface.PKTGEN_DPDK) as guest:
                guest.exec("echo hello world")


                # TODO rebuild fs

                # vhost_sock = "/tmp/vhost0.sock"
                # host.tmux_kill("Pktgen")
                # host.exec(f"sudo rm {vhost_sock} || true")
                # host.tmux_new("Pktgen", f"sudo pktgen -l 6,7,8,9 --vdev 'eth_vhost0,iface={vhost_sock}' -- -m '[0:3].0' -G")


                # guest.exec("modprobe virtio-net")
                # guest.exec("ip l set enp0s9 up")

                # remote_kmod_path = host.exec(f"realpath {PROJECT_ROOT}/.nix-builds/cvm-vfio").strip()
                # remote_kmod_path = f"home/Wallet-VMPL" # TODO someone needs to build these; dont hardcode VMPL4
                # guest.exec(f"rmmod vfio-pci || true; rmmod vfio-pci-core || true; rmmod vfio_iommu_type1 || true; rmmod vfio || true;")
                # guest.exec(f"modprobe irqbypass; insmod {remote_kmod_path}/linux/drivers/vfio/vfio.ko; insmod {remote_kmod_path}/linux/drivers/vfio/vfio_iommu_type1.ko; insmod {remote_kmod_path}/linux/drivers/vfio/pci/vfio-pci-core.ko; insmod {remote_kmod_path}/linux/drivers/vfio/pci/vfio-pci.ko")
                guest.exec("modprobe vfio-pci")
                guest.exec("insmod module/vmpl.ko")
                # guest.exec(f"dpdk-devbind.py -b vfio-pci {guest.test_iface_addr} --noiommu-mode")
                remote_dpdk_path = host.exec(f"realpath {PROJECT_ROOT}/.nix-builds/dpdk").strip()
                guest.exec(f"{remote_dpdk_path}/bin/dpdk-devbind.py -b vfio-pci {guest.test_iface_addr} --noiommu-mode")
                sleep(1) # for good measure
                remote_mirror_output = "/tmp/mirror_output.log"
                guest.exec(f"rm {remote_mirror_output} || true")
                # print("Manually run in guest and wait for 'Core 0 receiving packets': gdb --ex run --args ./module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa")
                # print("cd module/example-dpdk; gdb --ex run --args ./noiomgr_run -l 0 --no-huge --iova-mode=pa")
                # breakpoint()
                # guest.tmux_new("workload", f"gdb --ex run --args ./module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
                # guest.tmux_new("workload", f"cd module/example-dpdk; ./noiomgr_run -l 0 --no-huge --iova-mode=pa | tee {remote_mirror_output}")
                # guest.wait_for_success(f"grep 'Core 0 receiving packets.' {remote_mirror_output}", timeout=30)

                guest.exec("rm /tmp/.dpdk-running || true")
                # guest.tmux_new("workload", f"./module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
                guest.tmux_new("workload", f"cd ./module/example-dpdk; gdb -ex run --args ./noiomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
                # breakpoint()
                # sleep(30)
                # guest.wait_for_success(f"grep 'Core 0 receiving packets.' {remote_mirror_output}", timeout=30)
                guest.wait_for_success(f"test -f /tmp/.dpdk-running", timeout=30)

                # print(host.exec_pktgen('printf("asdfasdfasdf\\n")'))
                # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "rate"))')
                # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "port"))')
                # host.exec_pktgen('prints("pktStats", pktgen.portStats("0", "rate"))')
                host.exec_pktgen('pktgen.set("all", "size", 64)')
                host.exec_pktgen('pktgen.start(0)')
                sleep(3)
                pps = []
                for _ in range(5):
                    pps += [ int(host.exec_pktgen('printf(pktgen.portStats("0", "rate")[0].pkts_rx)')) ]
                    sleep(1)
                host.exec_pktgen('pktgen.stop(0)')

                print(f"Mean Mpps: {np.mean(pps)/1e6:.3f} (stddev: {np.std(pps)/1e6:.3f})")
                # breakpoint()
                # pass
                # command = 'printf("Hello from Python!\\n")'
                # script = f"""
                #     package.path = package.path .. ";{host.project_root}/pybench/Pktgen.lua;"
                #     require "Pktgen"
                #     {command}
                # """
                # print(host.exec(f"echo '{script}' | socat - TCP4:localhost:22022"))
                pass
            # host.start_vpp()
            # test.compile(host)
            # for repetition in range(test.repetitions):
            #     test.run(host, repetition)
            bench.done(test)

    # dfs = []
    # for test in tests:
    #     for repetition in range(test.repetitions):
    #         dfs += [ test.parse_results(repetition) ]
    # df = pd.concat(dfs)
    # df.to_csv(path_join(G.OUT_DIR, "userspace_summary.csv"))
    # with open(path_join(G.OUT_DIR, "userspace_summary.log"), 'w') as f:
    #     f.write(df.to_string())





if __name__ == "__main__":
    measurement = Measurement()
    main(measurement)
