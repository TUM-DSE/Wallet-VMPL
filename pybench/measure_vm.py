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

TARGET = {
    "polling": "build/polling_test-shared",
    "procedural": "build/procedural_test-shared",
    "noiomgr": "build/noiomgr_test-shared"
}

LLC_SIZE = 512*1024*1024 # 512 MB last level cache

@dataclass
class PktgenTest(AbstractBenchTest):

    batchsize: int
    workload: int # per packet per vnflet workload in ns
    chaining: int
    system: str # mirror, noiomgr, iomgr
    pktsize: int

    def test_infix(self):
        return f"userspace_{self.system}_b{self.batchsize}_{self.workload}ns_c{self.chaining}_{self.pktsize}b"

    def estimated_runtime(self) -> float:
        return 65 * self.repetitions # not very accurate, because every repetition requires a reboot which we don't consider accurately here

    @staticmethod
    def _read_pidfile(path: str):
        try:
            with open(path, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    def pre_initial_cleanup(self, host: Host, qemu_pid, pktgen_pid):
        debug('Pre-Initial cleanup (pktgen-specific)')
        try:
            host.kill_guest()
        except Exception:
            pass
        host.stop_pktgen_vhost()
        # sometimes qemu and pktgen refuse to die. Lets try not to kill other peoples processes though.
        username = getpass.getuser()
        if qemu_pid is None:
            qemu_pid = self._read_pidfile(f"/tmp/pidfile.{username}.qemu")
        if pktgen_pid is None:
            pktgen_pid = self._read_pidfile(f"/tmp/pidfile.{username}.pktgen")
        if qemu_pid is not None:
            host.exec(f"sudo kill {qemu_pid} || true")
        if pktgen_pid is not None:
            host.exec(f"sudo kill {pktgen_pid} || true")

    def compile(self, server: Server):
        cflags = " ".join([
            f"-DBURST_SIZE={self.batchsize}",
            f"-DPACKET_SIZE={self.pktsize}",
            f"-DPER_VNFLET_WORKLOAD_NS={self.workload}",
            # f"-DCHAINING={self.chaining}",
            # f"-DLLC_SIZE={LLC_SIZE}",
        ])

        trustlets = []
        dpdk_examples = []
        runners = []
        if self.system == "mirror":
            dpdk_examples = ["mirror"]
        elif self.system == "noiomgr":
            trustlets = ["noiomgr_trustlet"]
            runners = ["noiomgr_run"]
        elif self.system == "iomgr":
            trustlets = ["iomgr_trustlet"]
            runners = ["iomgr_run"]
        else:
            raise ValueError(f"Unknown system {self.system}")

        if len(trustlets) > 0:
            # limit what "all" target refers to with TRUSTLETS and DPDK_EXAMPLES
            server.exec(f"make -C {PROJECT_ROOT}/module/example-dpdk all -B TRUSTLETS=\"{' '.join(trustlets)}\" DPDK_EXAMPLES=\"{' '.join(dpdk_examples)}\" RUNNERS=\"{' '.join(runners)}\" CFLAGS=\"{cflags}\"")
        else:
            # without trustlets, make all will fail (more specifically building the fs)
            server.exec(f"make -C {PROJECT_ROOT}/module/example-dpdk {' '.join(dpdk_examples)} -B CFLAGS=\"{cflags}\"")

    def run(self, host: Server, guest: Server, repetition: int):
        if self.chaining != 1:
            raise NotImplementedError("Chaining > 1 not implemented")

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
        if self.system == "mirror":
            guest.tmux_new("workload", f"./module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa; sleep 999") # | tee {remote_mirror_output}")
        elif self.system == "noiomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; gdb -ex run --args ./noiomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        elif self.system == "iomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; gdb -ex run --args ./iomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        else:
            raise ValueError(f"Unknown system {self.system}")

        # breakpoint()
        # sleep(30)
        # guest.wait_for_success(f"grep 'Core 0 receiving packets.' {remote_mirror_output}", timeout=30)
        guest.wait_for_success(f"test -f /tmp/.dpdk-running", timeout=180)

        # print(host.exec_pktgen('printf("asdfasdfasdf\\n")'))
        # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "rate"))')
        # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "port"))')
        # host.exec_pktgen('prints("pktStats", pktgen.portStats("0", "rate"))')
        host.exec_pktgen(f'pktgen.set("all", "size", {self.pktsize})')
        host.exec_pktgen('pktgen.start(0)')
        sleep(3)
        pps = []
        for _ in range(5):
            lua = """
                printf(pktgen.portStats("0", "rate")[0].pkts_rx)
            """
            pps += [ int(host.exec_pktgen(lua)) ]
            sleep(1)
        host.exec_pktgen('pktgen.stop(0)')

        pkt_counts = host.exec_pktgen('printf(pktgen.portStats("0", "port")[0].opackets .. "/" .. pktgen.portStats("0", "port")[0].ipackets)').split("/")

        print(f"Mean Mpps: {np.mean(pps)/1e6:.3f} (stddev: {np.std(pps)/1e6:.3f})")
        print(f"Total pktgen packets: {pkt_counts[0]} tx, {pkt_counts[1]} rx")

        local_output_file = self.output_filepath(repetition)
        os.makedirs(os.path.dirname(local_output_file), exist_ok=True)
        data = []
        for foo in pps:
            data += [{
                **asdict(self),
                "repetition": repetition,
                "Mpps": foo/1e6
            }]
        df = DataFrame(data=data)
        df.to_csv(local_output_file, index=False)

        # remote_output_file = "/tmp/output.log"
        # local_output_file = self.output_filepath(repetition)
        # server.exec(f"sudo {PROJECT_ROOT}/{TARGET[self.system]} -l 0,6-12 > {remote_output_file} 2>&1")
        # server.copy_from(remote_output_file, local_output_file)
        # pass


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
    tests : List[PktgenTest] = []
    basic_tests = dict(
        repetitions=[2],
        batchsize = [1, 32],
        workload = [ 0 ],
        chaining = [1],
        system = [ "mirror", "iomgr", "noiomgr" ],
        pktsize = [ 64, 1500 ],

        # legacy args
        num_vms = [0],
    )
    workload_tests_64b = dict(
        workload = [ 0, 1, 5, 10, 20, 40, 80, 160, 320, 640, 1280 ],
        system = [ "mirror", "iomgr", "noiomgr" ],
        pktsize = [ 64 ],
        repetitions=[2], batchsize = [32], chaining = [1], num_vms = [0],
    )
    workload_tests_1500b = dict(
        workload = [ int(i) for i in np.linspace(0, 2000, 10) ],
        system = [ "mirror", "iomgr", "noiomgr" ],
        pktsize = [ 1500 ],
        repetitions=[2], batchsize = [32], chaining = [1], num_vms = [0],
    )
    tests = PktgenTest.list_tests(basic_tests) + PktgenTest.list_tests(workload_tests_64b) + PktgenTest.list_tests(workload_tests_1500b)

    if G.BRIEF:
        LLC_SIZE = 512*1024 # reduce memory consumption for laptops
        test_matrix = dict(
            repetitions=[1],
            batchsize = [32], # , 32],
            workload = [ 0 ], # , 100 ],
            chaining = [1],
            # system = [ "mirror" ],
            system = [ "noiomgr", "iomgr" ],
            # system = [ "mirror", "noiomgr" ],
            pktsize = [ 64 ],

            # legacy args
            num_vms = [0],
        )
        test_matrix = measurement.apply_cmdline_overrides(test_matrix)
        tests = PktgenTest.list_tests(test_matrix)

    PktgenTest.estimate_time2(tests, [])

    if plan_only:
        return

    qemu_pid = None
    pktgen_pid = None

    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for [repetitions, batchsize, workload, chaining, system, pktsize], a_tests in bench.multi_iterator(bench_tests, ["repetitions", "batchsize", "workload", "chaining", "system", "pktsize"]):
            assert len(a_tests) == 1 # we have looped through all variables now, right?
            test = a_tests[0]
            info(f"Running {test}")
            test.compile(host)
            for repetition in range(test.repetitions):
                test.pre_initial_cleanup(host, qemu_pid, pktgen_pid)
                host.start_pktgen_vhost()
                pktgen_pid = host.tmux_get_pid("pktgen")
                with open(f"/tmp/pidfile.{getpass.getuser()}.pktgen", "w") as f:
                    f.write(str(pktgen_pid))
                # sleep(1) # wait and pray for pktgen
                with measurement.virtual_machine(Interface.PKTGEN_DPDK) as guest:
                    qemu_pid = host.tmux_get_pid("qemu")
                    with open(f"/tmp/pidfile.{getpass.getuser()}.qemu", "w") as f:
                        f.write(str(qemu_pid))


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

                    measurement.mark_vm_initialized(0)

                    test.run(host, guest, repetition)

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

    test.pre_initial_cleanup(host, qemu_pid, pktgen_pid)

    dfs = []
    for test in tests:
        for repetition in range(test.repetitions):
            dfs += [ pd.read_csv(test.output_filepath(repetition)) ]
    df = pd.concat(dfs)
    del df['repetition']
    df = df.groupby([ col for col in df.columns if col != "Mpps" ]).describe()
    df.to_csv(path_join(G.OUT_DIR, "vm_summary.csv"))
    with open(path_join(G.OUT_DIR, "vm_summary.log"), 'w') as f:
        f.write(df.to_string())





if __name__ == "__main__":
    measurement = Measurement(test_type=PktgenTest, supports_boot_only=True)
    main(measurement)
