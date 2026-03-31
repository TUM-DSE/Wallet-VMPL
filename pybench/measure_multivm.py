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
from enums import Interface, MultiHost
from time import sleep
import os
import getpass
from util import safe_cast, deduplicate

LLC_SIZE = 512*1024*1024 # 512 MB last level cache
PREFIX = "emptyprefix"

@dataclass
class PktgenMultiVMTest(AbstractBenchTest):

    batchsize: int
    workload: int # per packet per vnflet workload in ns
    memory_workload: int # per packet per vnflet memory workload in bytes
    real_workload: str # synthetic or real
    chaining: int
    system: str # mirror, noiomgr, iomgr, insecure
    pktsize: int

    def test_infix(self):
        return f"{PREFIX}_{self.system}_{self.real_workload}_b{self.batchsize}_{self.workload}ns_{self.memory_workload}b_c{self.chaining}_v{self.num_vms}_{self.pktsize}b"

    def estimated_runtime(self) -> float:
        return 65 * self.repetitions # not very accurate, because every repetition requires a reboot which we don't consider accurately here

    @staticmethod
    def _read_pidfile(path: str):
        try:
            with open(path, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def pre_initial_cleanup(host: Host, qemu_pid, pktgen_pid):
        debug('Pre-Initial cleanup (pktgen-specific)')
        try:
            host.kill_guest()
        except Exception:
            pass
        host.stop_pktgen_vhost()
        # sometimes qemu and pktgen refuse to die. Lets try not to kill other peoples processes though.
        username = getpass.getuser()
        if qemu_pid is None:
            qemu_pid = PktgenMultiVMTest._read_pidfile(f"/tmp/pidfile.{username}.qemu")
        if pktgen_pid is None:
            pktgen_pid = PktgenMultiVMTest._read_pidfile(f"/tmp/pidfile.{username}.pktgen")
        if qemu_pid is not None:
            host.exec(f"sudo kill {qemu_pid} || true")
        if pktgen_pid is not None:
            host.exec(f"sudo kill {pktgen_pid} || true")

    def compile(self, server: Server):
        assert self.real_workload in [ "synthetic", "real" ], f"Unknown real_workload value {self.real_workload}"

        cflags = " ".join([
            f"-DBURST_SIZE={self.batchsize}",
            f"-DPACKET_SIZE={self.pktsize}",
            f"-DPER_VNFLET_WORKLOAD_NS={self.workload}",
            f"-DWORKLOAD_ACCESSES_B={self.memory_workload}",
            f"-DCHAINING={1}", # we abuse mirror here. Since we have multiple mirror instances, each one must assume to handle only 1 VNFlet
            # f"-DCHAINING={self.chaining}",
            # f"-DLLC_SIZE={LLC_SIZE}",
        ] + (
            [ "-DREAL_WORKLOAD=1" ] if self.real_workload == "real" else []
        ))

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
        elif self.system == "insecure":
            dpdk_examples = ["insecure"]
        else:
            raise ValueError(f"Unknown system {self.system}")

        if len(trustlets) > 0:
            # limit what "all" target refers to with TRUSTLETS and DPDK_EXAMPLES
            server.exec(f"make -C {PROJECT_ROOT}/module/example-dpdk all -B TRUSTLETS=\"{' '.join(trustlets)}\" DPDK_EXAMPLES=\"{' '.join(dpdk_examples)}\" RUNNERS=\"{' '.join(runners)}\" CFLAGS=\"{cflags}\"")
        else:
            # without trustlets, make all will fail (more specifically building the fs)
            server.exec(f"make -C {PROJECT_ROOT}/module/example-dpdk {' '.join(dpdk_examples)} -B CFLAGS=\"{cflags}\"")

    def start(self, host: Server, guest: Server, repetition: int):
        if self.chaining == 1:
            raise NotImplementedError("Chaining == 1 not implemented")

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
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./noiomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        elif self.system == "iomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./iomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        elif self.system == "insecure":
            guest.tmux_new("workload", f"cd module/example-dpdk; ./insecure --no-huge -l 0-{self.chaining} --iova-mode=pa")
        else:
            raise ValueError(f"Unknown system {self.system}")

        # breakpoint()
        # sleep(30)
        # guest.wait_for_success(f"grep 'Core 0 receiving packets.' {remote_mirror_output}", timeout=30)
        guest.wait_for_success(f"test -f /tmp/.dpdk-running", timeout=180)

    def measure(self, host: Server, repetition: int):
        if PREFIX == "multivm_lat":
            return self.measure_latency(host, repetition)
        elif PREFIX == "multivm":
            return self.measure_throughput(host, repetition)
        else:
            assert False, f"Unknown prefix {PREFIX}"

    def measure_throughput(self, host: Server, repetition: int):
        # print(host.exec_pktgen('printf("asdfasdfasdf\\n")'))
        # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "rate"))')
        # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "port"))')
        # host.exec_pktgen('prints("pktStats", pktgen.portStats("0", "rate"))')
        host.exec_pktgen(f'pktgen.set("all", "size", {self.pktsize})')
        host.exec_pktgen('pktgen.start(0)')
        sleep(3)
        pps = []
        for _ in range(G.DURATION_S):
            lua = """
                printf(pktgen.portStats("0", "rate")[0].pkts_rx)
            """
            pps += [ int(host.exec_pktgen(lua)) ]
            sleep(1)
        host.exec_pktgen('pktgen.stop(0)')

        pkt_counts = host.exec_pktgen('printf(pktgen.portStats("0", "port")[0].opackets .. "/" .. pktgen.portStats("0", "port")[0].ipackets)').split("/")

        print(f"Mean Mpps: {np.mean(pps)/1e6:.3f} (stddev: {np.std(pps)/1e6:.3f})")
        print(f"Total pktgen packets: {pkt_counts[0]} tx, {pkt_counts[1]} rx")

        # breakpoint()

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
        df["chaining"] = df["num_vms"] # we dont want to set them to equal in the text matrix already, because that would increse the test list generated from the matrix
        df.to_csv(local_output_file, index=False)

        # remote_output_file = "/tmp/output.log"
        # local_output_file = self.output_filepath(repetition)
        # server.exec(f"sudo {PROJECT_ROOT}/{TARGET[self.system]} -l 0,6-12 > {remote_output_file} 2>&1")
        # server.copy_from(remote_output_file, local_output_file)
        # pass

    def measure_latency(self, host: Server, repetition: int):
        local_output_file = self.output_filepath(repetition)
        remote_csv_file = "/tmp/lat.csv"
        local_csv_file = self.output_filepath(repetition, extension="csv")
        host.exec(f"sudo rm {remote_csv_file} || true")
        # host.tmux_new("perf", "sudo perf record -F 1000 -a -g -- sleep 20")
        # host.tmux_new("perf", "sudo perf sched record -a -o perf_sched.data -- sleep 20")

        # print(host.exec_pktgen('printf("asdfasdfasdf\\n")'))
        # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "rate"))')
        # host.exec_pktgen('prints("portStats", pktgen.portStats("0", "port"))')
        # host.exec_pktgen('prints("pktStats", pktgen.portStats("0", "rate"))')
        host.exec_pktgen(f'pktgen.set("all", "size", {self.pktsize})') # 100mbit
        host.exec_pktgen(f'pktgen.set("all", "rate", 0.1)')
        host.exec_pktgen('pktgen.start(0)')
        host.exec_pktgen(f'pktgen.latency("all", "enable")')
        host.exec_pktgen(f'pktgen.latsampler_params(0, "simple", 10000, 1000, "{remote_csv_file}")') # 10k samples (whatever many we can get), 1000Hz
        host.exec_pktgen(f'pktgen.latsampler("all", "enable")')
        # host.exec_pktgen(f'pktgen.capture_latency("all", "enable")')
        # host.exec_pktgen(f'pktgen.capture("all", "enable")')

        sleep(3)
        lat_us = []
        for _ in range(G.DURATION_S):
            lua = """
                printf(pktgen.pktStats(0)[0].latency.avg_us)
            """
            result_string = host.exec_pktgen(lua)
            lat_us += [ float(result_string) ]
            sleep(1)

        # host.exec_pktgen(f'pktgen.capture_latency("all", "disable")')
        # host.exec_pktgen(f'pktgen.capture("all", "disable")')
        # sleep(1)
        # breakpoint()
        host.exec_pktgen(f'pktgen.latsampler("all", "disable")')
        host.exec_pktgen(f'pktgen.latency("all", "disable")')
        host.exec_pktgen('pktgen.stop(0)')

        pkt_counts = host.exec_pktgen('printf(pktgen.portStats("0", "port")[0].opackets .. "/" .. pktgen.portStats("0", "port")[0].ipackets)').split("/")

        print(f"Mean latency: {np.mean(lat_us):.3f} us (stddev: {np.std(lat_us):.3f} us)")
        print(f"Total pktgen packets: {pkt_counts[0]} tx, {pkt_counts[1]} rx")


        if np.mean(lat_us) > 2000:
            print(host.exec("date"))
            # breakpoint()

        os.makedirs(os.path.dirname(local_output_file), exist_ok=True)
        host.copy_from(remote_csv_file, local_csv_file)
        data = []
        for foo in lat_us:
            data += [{
                **asdict(self),
                "repetition": repetition,
                "lat_us": foo
            }]
        df = DataFrame(data=data)
        df["chaining"] = df["num_vms"] # we dont want to set them to equal in the text matrix already, because that would increse the test list generated from the matrix
        df.to_csv(local_output_file, index=False)




def main(measurement: Measurement, plan_only: bool = False, mode: str = "throughput") -> None:
    global LLC_SIZE
    global PREFIX
    assert mode in ["throughput", "latency"], f"Unknown mode {mode}"
    if mode == "latency":
        PREFIX = "multivm_lat"
    elif mode == "throughput":
        PREFIX = "multivm"
    host, loadgen = measurement.hosts()
    tests : List[PktgenMultiVMTest] = []
    G.DURATION_S = 15
    REPETITIONS = 2
    if measurement.args.extremes_only:
        G.DURATION_S = 5
        REPETITIONS = 1

    basic_tests = dict(
        repetitions=[REPETITIONS],
        batchsize = [1, 32],
        workload = [ 0 ],
        memory_workload = [ 0 ],
        real_workload = [ "synthetic" ],
        num_vms = [2],
        system = [ "mirror" ],
        pktsize = [ 64, 1500 ],

        # legacy args, chaining is now num_vms
        chaining = [0],
    )
    workload_tests_64b = dict(
        workload = [ 0, 1, 5, 10, 20, 40, 80, 160, 320, 640, 1280 ],
        system = [ "mirror" ],
        pktsize = [ 64 ],
        real_workload = [ "synthetic" ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], chaining = [0], num_vms = [2],
    )
    workload_tests_1500b = dict(
        workload = [ int(i) for i in np.linspace(0, 2000, 10) ],
        system = [ "mirror" ],
        pktsize = [ 1500 ],
        real_workload = [ "synthetic" ], memory_workload = [ 0 ], repetitions=[2], batchsize = [32], chaining = [0], num_vms = [2],
    )
    memory_workload_tests = dict(
        memory_workload = [ int(i) for i in np.linspace(0, 0x1000, 10) ],
        system = [ "mirror" ],
        pktsize = [ 64, 1500 ],
        real_workload = [ "synthetic" ], workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], chaining = [0], num_vms = [2],
    )
    chaining_tests = dict(
        system = [ "mirror" ],
        pktsize = [ 64, 1500 ],
        num_vms = [2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 32],
        real_workload = [ "synthetic" ], workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32],
        # legacy args, chaining is now num_vms
        chaining = [0],
    )
    real_workload_tests = dict(
        system = [ "mirror" ],
        pktsize = [ 64, 128, 256, 512, 1024, 1500 ],
        num_vms = [ 3 ],
        real_workload = [ "real" ],
        workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32],
        # legacy args, chaining is now num_vms
        chaining = [0],
    )
    tests = \
        PktgenMultiVMTest.list_tests(basic_tests) + \
        PktgenMultiVMTest.list_tests(workload_tests_64b) + \
        PktgenMultiVMTest.list_tests(workload_tests_1500b) + \
        PktgenMultiVMTest.list_tests(memory_workload_tests) + \
        PktgenMultiVMTest.list_tests(chaining_tests) + \
        (PktgenMultiVMTest.list_tests(real_workload_tests) if mode != "latency" else [])

    if G.BRIEF:
        LLC_SIZE = 512*1024 # reduce memory consumption for laptops
        G.DURATION_S = 30
        test_matrix = dict(
            repetitions=[1],
            batchsize = [32], # , 32],
            workload = [ 0 ], # , 100 ],
            memory_workload = [ 0 ],
            real_workload = [ "synthetic" ],
            num_vms = [2],
            system = [ "mirror" ],
            # system = [ "noiomgr", "iomgr", "mirror", "insecure" ],
            # system = [ "mirror", "noiomgr" ],
            pktsize = [ 64 ],
            # legacy args, chaining is now num_vms
            chaining = [0],
        )
        test_matrix = measurement.apply_cmdline_overrides(test_matrix)
        tests = PktgenMultiVMTest.list_tests(test_matrix)


    tests = deduplicate(tests)
    test_params = ["repetitions", "num_vms", "batchsize", "workload", "memory_workload", "real_workload", "chaining", "system", "pktsize"] #  define iteration order
    assert sorted(test_params) == sorted(PktgenMultiVMTest.test_parameters())
    if measurement.args.extremes_only:
        tests = PktgenMultiVMTest.filter_extremes(tests, test_params)
    PktgenMultiVMTest.estimate_time2(tests, [])

    if plan_only:
        return

    qemu_pid = None
    pktgen_pid = None

    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for _param_dict, a_tests in bench.multi_iterator_dict(bench_tests, test_params):
            assert len(a_tests) == 1 # we have looped through all variables now, right?
            test = a_tests[0]
            assert test.chaining == 0 # we've replaced chaining with num_vms
            info(f"Running {test}")
            test.compile(host)
            for repetition in range(test.repetitions):
                PktgenMultiVMTest.pre_initial_cleanup(host, qemu_pid, pktgen_pid)
                # sleep(1) # wait and pray for pktgen
                vm_args = { 'vcpus': 1 }
                with measurement.virtual_machines(Interface.VPP, num=test.num_vms, run_guest_args=vm_args) as guests:

                    # start pktgen after the VM because VPP is not the vhost server
                    host.start_pktgen_vhost(connect_to_vpp = True)
                    pktgen_pid = host.tmux_get_pid("pktgen")
                    with open(f"/tmp/pidfile.{getpass.getuser()}.pktgen", "w") as f:
                        f.write(str(pktgen_pid))

                    qemu_pid = ""
                    for vm_number, guest in guests.items():
                        qemu_pid += str(host.tmux_get_pid(MultiHost.enumerate('qemu', vm_number)))
                        qemu_pid += " "
                    # qemu_pid = host.tmux_get_pid("qemu")
                    with open(f"/tmp/pidfile.{getpass.getuser()}.qemu", "w") as f:
                        f.write(str(qemu_pid))


                    remote_dpdk_path = host.exec(f"realpath {PROJECT_ROOT}/.nix-builds/dpdk").strip()
                    def foreach_parallel(i, guest): # pyright: ignore[reportGeneralTypeIssues]
                        guest.exec("modprobe vfio-pci")
                        guest.exec("insmod module/vmpl.ko")
                        guest.exec(f"{remote_dpdk_path}/bin/dpdk-devbind.py -b vfio-pci {guest.test_iface_addr} --noiommu-mode")
                    end_foreach(guests, foreach_parallel)

                    for vm_number, guest in guests.items():
                        measurement.mark_vm_initialized(vm_number)

                    def foreach_parallel(i, guest): # pyright: ignore[reportGeneralTypeIssues]
                        test.start(host, guest, repetition)
                    end_foreach(guests, foreach_parallel)


                    error("foo")
                    test.measure(host, repetition)

                    pass
            bench.done(test)

    PktgenMultiVMTest.pre_initial_cleanup(host, qemu_pid, pktgen_pid)

    dfs = []
    for test in tests:
        for repetition in range(test.repetitions):
            dfs += [ pd.read_csv(test.output_filepath(repetition)) ]
    df = pd.concat(dfs)
    del df['repetition']
    if mode == "latency":
        df = df.groupby([ col for col in df.columns if col != "lat_us" ]).describe()
    elif mode == "throughput":
        df = df.groupby([ col for col in df.columns if col != "Mpps" ]).describe()
    df.to_csv(path_join(G.OUT_DIR, f"{PREFIX}_summary.csv"))
    with open(path_join(G.OUT_DIR, f"{PREFIX}_summary.log"), 'w') as f:
        f.write(df.to_string())





if __name__ == "__main__":
    def add_args(parser):
        parser.add_argument('--latency',
                            action='store_true',
                            help='Measure latency instead of throughput.',
                            )
    measurement = Measurement(test_type=PktgenMultiVMTest, supports_boot_only=True, arg_lambda=add_args)
    main(measurement, mode="latency" if measurement.args.latency else "throughput")
