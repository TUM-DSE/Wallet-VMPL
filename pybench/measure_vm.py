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
from util import safe_cast, deduplicate
from datetime import datetime

LLC_SIZE = 512*1024*1024 # 512 MB last level cache
PREFIX = "emptyprefix"

@dataclass
class PktgenTest(AbstractBenchTest):

    batchsize: int
    workload: int # per packet per vnflet workload in ns
    memory_workload: int # per packet per vnflet memory workload in bytes
    real_workload: str # synthetic or real
    chaining: int
    system: str # mirror, noiomgr, iomgr, insecure
    pktsize: int

    def test_infix(self):
        return f"{PREFIX}_{self.system}_{self.real_workload}_b{self.batchsize}_{self.workload}ns_{self.memory_workload}b_c{self.chaining}_{self.pktsize}b"

    def estimated_runtime(self) -> float:
        measurement_time = G.DURATION_S + 3
        c = max(self.chaining, 2)
        if self.system == "iomgr":
            boot_overhead = 95 + 6 * c
        elif self.system == "noiomgr":
            boot_overhead = 85 + 6 * c
        elif self.system in ("insecure", "mirror"):
            boot_overhead = 50 + 4 * c ** 1.5
        else:
            boot_overhead = 100
        return (boot_overhead + measurement_time) * self.repetitions

    @staticmethod
    def _read_pidfile(path: str):
        try:
            with open(path, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def _get_child_pids(host: Host, pid: int):
        """Return list of (child_pid, exe_name) for all children of pid."""
        try:
            output = host.exec(f"ps --ppid {pid} -o pid=,comm= 2>/dev/null || true").strip()
        except Exception:
            return []
        children = []
        for line in output.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                child_pid, exe_name = int(parts[0]), parts[1]
                children.append((child_pid, exe_name))
        return children

    @staticmethod
    def _check_survivors(host: Host, pids):
        """Check which pids from the list are still alive and log them."""
        survivors = []
        for pid, exe_name in pids:
            result = host.exec(f"kill -0 {pid} 2>/dev/null && echo alive || echo dead").strip()
            if result == "alive":
                survivors.append((pid, exe_name))
        if survivors:
            warning(f"Processes still alive after kill: {survivors}")
        return survivors

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
            qemu_pid = PktgenTest._read_pidfile(f"/tmp/pidfile.{username}.qemu")
        if pktgen_pid is None:
            pktgen_pid = PktgenTest._read_pidfile(f"/tmp/pidfile.{username}.pktgen")

        all_children = []
        for pid, label in [(qemu_pid, "qemu"), (pktgen_pid, "pktgen")]:
            if pid is not None:
                children = PktgenTest._get_child_pids(host, pid)
                if children:
                    debug(f"Children of {label} (pid {pid}): {children}")
                all_children.extend(children)
                host.exec(f"sudo kill {pid} || true")

        if all_children:
            for attempt in range(6):
                survivors = PktgenTest._check_survivors(host, all_children)
                if not survivors:
                    break
                warning(f"Retry {attempt + 1}/3: killing {len(survivors)} surviving children")
                for pid, _exe_name in survivors:
                    host.exec(f"sudo kill -9 {pid} || true")
                sleep(1)

    def compile(self, server: Server):
        assert self.real_workload in [ "synthetic", "real" ], f"Unknown real_workload value {self.real_workload}"

        cflags = " ".join([
            f"-DBURST_SIZE={self.batchsize}",
            f"-DPACKET_SIZE={self.pktsize}",
            f"-DPER_VNFLET_WORKLOAD_NS={self.workload}",
            f"-DWORKLOAD_ACCESSES_B={self.memory_workload}",
            f"-DCHAINING={self.chaining}",
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


        # In our measurements, the default DPDK mempool has suboptimal performance. Use SIMPLE_POOL to use the same pool as Slick, or use DPDK's stack pool which has the same performance.
        dpdk_mbuf_pool_type = "--mbuf-pool-ops-name='stack'"

        guest.exec("rm /tmp/.dpdk-running || true")
        time_start = datetime.now()
        if self.system == "mirror":
            guest.tmux_new("workload", f"./module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa {dpdk_mbuf_pool_type}; sleep 999") # | tee {remote_mirror_output}")
        elif self.system == "noiomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./noiomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        elif self.system == "iomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./iomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        elif self.system == "insecure":
            expected_usage_mb = (self.chaining + 2) * 12  # ~12MB per chain level for mbufs
            assert 1024 > expected_usage_mb, "You probably have to raise the -m value"
            cmd = "cd module/example-dpdk; "
            # cmd += "/nix/store/5lqv1pfaacwg2w7nd0qpcx2b5c4cmk1v-gdb-14.2/bin/gdb --args "
            cmd += f"./insecure -m 512M --no-huge -l 0-{self.chaining} --iova-mode=pa {dpdk_mbuf_pool_type}; "
            cmd += "sleep 999"
            guest.tmux_new("workload", cmd)
        else:
            raise ValueError(f"Unknown system {self.system}")

        # breakpoint()
        # sleep(30)
        # guest.wait_for_success(f"grep 'Core 0 receiving packets.' {remote_mirror_output}", timeout=30)
        guest.wait_for_success("test -f /tmp/.dpdk-running", timeout=90*max(self.num_vms, self.chaining)) # with long chains, we have to expect up to 80s per VNFlet
        time_end = datetime.now()
        print(f"Slick start time: {(time_end - time_start).total_seconds():.2f} seconds")


    def measure(self, host: Server, guest: Server, repetition: int):
        if PREFIX == "vm_lat":
            return self.measure_latency(host, guest, repetition)
        elif PREFIX == "vm":
            return self.measure_throughput(host, guest, repetition)
        else:
            assert False, f"Unknown prefix {PREFIX}"

    def measure_throughput(self, host: Server, guest: Server, repetition: int):
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
        df.to_csv(local_output_file, index=False)

        # remote_output_file = "/tmp/output.log"
        # local_output_file = self.output_filepath(repetition)
        # server.exec(f"sudo {PROJECT_ROOT}/{TARGET[self.system]} -l 0,6-12 > {remote_output_file} 2>&1")
        # server.copy_from(remote_output_file, local_output_file)
        # pass

    def measure_latency(self, host: Server, guest: Server, repetition: int):
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
        df.to_csv(local_output_file, index=False)


def main(measurement: Measurement, plan_only: bool = False, mode: str = "throughput") -> None:
    global LLC_SIZE
    global PREFIX
    assert mode in ["throughput", "latency"], f"Unknown mode {mode}"
    if mode == "latency":
        PREFIX = "vm_lat"
    elif mode == "throughput":
        PREFIX = "vm"
    host, loadgen = measurement.hosts()
    tests : List[PktgenTest] = []
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
        chaining = [2],
        system = [ "iomgr", "noiomgr", "insecure" ],
        pktsize = [ 64, 1500 ],

        # legacy args
        num_vms = [0],
    )
    workload_tests_64b = dict(
        workload = [ 0, 1, 5, 10, 20, 40, 80, 160, 320, 640, 1280 ],
        system = [ "iomgr", "noiomgr", "insecure" ],
        pktsize = [ 64 ],
        real_workload = [ "synthetic" ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], chaining = [2], num_vms = [0],
    )
    workload_tests_1500b = dict(
        workload = [ int(i) for i in np.linspace(0, 2000, 10) ],
        system = [ "iomgr", "noiomgr", "insecure" ],
        pktsize = [ 1500 ],
        real_workload = [ "synthetic" ], memory_workload = [ 0 ], repetitions=[2], batchsize = [32], chaining = [2], num_vms = [0],
    )
    memory_workload_tests = dict(
        memory_workload = [ int(i) for i in np.linspace(0, 0x1000, 10) ],
        system = [ "iomgr", "noiomgr", "insecure" ],
        pktsize = [ 64, 1500 ],
        real_workload = [ "synthetic" ], workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], chaining = [2], num_vms = [0],
    )
    chaining_tests = dict(
        system = [ "iomgr", "noiomgr", "insecure" ],
        pktsize = [ 64, 1500 ],
        chaining = [2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 32],
        real_workload = [ "synthetic" ], workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], num_vms = [0],
    )
    real_workload_tests = dict(
        system = [ "iomgr", "noiomgr", "insecure" ],
        pktsize = [ 64, 128, 256, 512, 1024, 1500 ],
        real_workload = [ "real" ],
        chaining = [ 3 ], workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], num_vms = [0],
    )
    tests = \
        PktgenTest.list_tests(basic_tests) + \
        PktgenTest.list_tests(workload_tests_64b) + \
        PktgenTest.list_tests(workload_tests_1500b) + \
        PktgenTest.list_tests(memory_workload_tests) + \
        PktgenTest.list_tests(chaining_tests) + \
        (PktgenTest.list_tests(real_workload_tests) if mode != "latency" else [])

    if G.BRIEF:
        LLC_SIZE = 512*1024 # reduce memory consumption for laptops
        G.DURATION_S = 5
        test_matrix = dict(
            repetitions=[1],
            batchsize = [32], # , 32],
            workload = [ 0 ], # , 100 ],
            memory_workload = [ 0 ],
            real_workload = [ "synthetic" ],
            chaining = [2],
            # system = [ "mirror" ],
            system = [ "noiomgr", "iomgr", "insecure" ],
            # system = [ "mirror", "noiomgr" ],
            pktsize = [ 64 ],

            # legacy args
            num_vms = [0],
        )
        test_matrix = measurement.apply_cmdline_overrides(test_matrix)
        tests = PktgenTest.list_tests(test_matrix)


    tests = deduplicate(tests)
    test_params = ["repetitions", "num_vms", "batchsize", "workload", "memory_workload", "real_workload", "chaining", "system", "pktsize"] #  define iteration order
    assert sorted(test_params) == sorted(PktgenTest.test_parameters())
    if measurement.args.extremes_only:
        tests = PktgenTest.filter_extremes(tests, test_params)
    PktgenTest.estimate_time2(tests, [])

    if plan_only:
        return

    qemu_pid = None
    pktgen_pid = None

    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for _param_dict, a_tests in bench.multi_iterator_dict(bench_tests, test_params):
            assert len(a_tests) == 1 # we have looped through all variables now, right?
            test = a_tests[0]
            info(f"Running {test}")
            test.compile(host)
            for repetition in range(test.repetitions):
                PktgenTest.pre_initial_cleanup(host, qemu_pid, pktgen_pid)
                host.start_pktgen_vhost()
                pktgen_pid = host.tmux_get_pid("pktgen")
                with open(f"/tmp/pidfile.{getpass.getuser()}.pktgen", "w") as f:
                    f.write(str(pktgen_pid))
                # sleep(1) # wait and pray for pktgen
                with measurement.virtual_machine(Interface.PKTGEN_DPDK) as guest:
                    qemu_pid = host.tmux_get_pid("qemu")
                    with open(f"/tmp/pidfile.{getpass.getuser()}.qemu", "w") as f:
                        f.write(str(qemu_pid))

                    # guest.exec("rmmod vfio-pci || true;")
                    # guest.exec("rmmod vfio-pci-core || true;")
                    # guest.exec("rmmod vfio_iommu_type1 || true")
                    # guest.exec("rmmod vfio || true")
                    # guest.exec("modprobe irqbypass || true")
                    # guest.exec("insmod ./home/Wallet-VMPL4/linux/drivers/vfio/vfio.ko")
                    # guest.exec("insmod ./home/Wallet-VMPL4/linux/drivers/vfio/vfio_iommu_type1.ko")
                    # guest.exec("insmod ./home/Wallet-VMPL4/linux/drivers/vfio/pci/vfio-pci-core.ko")
                    # guest.exec("insmod ./home/Wallet-VMPL4/linux/drivers/vfio/pci/vfio-pci.ko")

                    guest.exec("modprobe vfio-pci")
                    guest.exec("insmod module/vmpl.ko")
                    remote_dpdk_path = host.exec(f"realpath {PROJECT_ROOT}/.nix-builds/dpdk").strip()
                    guest.exec(f"{remote_dpdk_path}/bin/dpdk-devbind.py -b vfio-pci {guest.test_iface_addr} --noiommu-mode")

                    measurement.mark_vm_initialized(0)

                    test.start(host, guest, repetition)
                    test.measure(host, guest, repetition)

                    # breakpoint()
                    pass
            bench.done(test)

    PktgenTest.pre_initial_cleanup(host, qemu_pid, pktgen_pid)

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
    measurement = Measurement(test_type=PktgenTest, supports_boot_only=True, arg_lambda=add_args)
    main(measurement, mode="latency" if measurement.args.latency else "throughput")
