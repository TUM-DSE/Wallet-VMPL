from measure import Bench, AbstractBenchTest, Measurement, end_foreach
from measure_vm import PktgenTest
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

LLC_SIZE = 512*1024*1024 # 512 MB last level cache

@dataclass
class PktgenLatencyTest(PktgenTest):

    # inherited from PktgenTest:
    # batchsize: int
    # workload: int # per packet per vnflet workload in ns
    # chaining: int
    # system: str # mirror, noiomgr, iomgr
    # pktsize: int

    def test_infix(self):
        return f"vm_lat_{self.system}_b{self.batchsize}_{self.workload}ns_c{self.chaining}_{self.pktsize}b"

    def measure(self, host: Server, guest: Server, repetition: int):
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

        # remote_output_file = "/tmp/output.log"
        # local_output_file = self.output_filepath(repetition)
        # server.exec(f"sudo {PROJECT_ROOT}/{TARGET[self.system]} -l 0,6-12 > {remote_output_file} 2>&1")
        # server.copy_from(remote_output_file, local_output_file)
        # pass




def main(measurement: Measurement, plan_only: bool = False) -> None:
    global LLC_SIZE
    host, loadgen = measurement.hosts()
    tests : List[PktgenLatencyTest] = []
    G.DURATION_S = 5
    basic_tests = dict(
        repetitions=[2],
        batchsize = [1, 32],
        workload = [ 0 ],
        memory_workload = [ 0 ],
        chaining = [2],
        system = [ "mirror", "iomgr", "noiomgr" ],
        pktsize = [ 64, 128, 1500 ],

        # legacy args
        num_vms = [0],
    )
    workload_tests_64b = dict(
        workload = [ 0, 1, 5, 10, 20, 40, 80, 160, 320, 640, 1280 ],
        system = [ "mirror", "iomgr", "noiomgr" ],
        pktsize = [ 64, 128 ],
        memory_workload = [ 0 ], repetitions=[2], batchsize = [32], chaining = [2], num_vms = [0],
    )
    workload_tests_1500b = dict(
        workload = [ int(i) for i in np.linspace(0, 2000, 10) ],
        system = [ "mirror", "iomgr", "noiomgr" ],
        pktsize = [ 1500 ],
        memory_workload = [ 0 ], repetitions=[2], batchsize = [32], chaining = [2], num_vms = [0],
    )
    tests = PktgenLatencyTest.list_tests(basic_tests) + PktgenLatencyTest.list_tests(workload_tests_64b) + PktgenLatencyTest.list_tests(workload_tests_1500b)

    if G.BRIEF:
        LLC_SIZE = 512*1024 # reduce memory consumption for laptops
        test_matrix = dict(
            repetitions=[1],
            batchsize = [32], # , 32],
            workload = [ 0 ], # , 100 ],
            memory_workload = [ 0 ],
            chaining = [2],
            # system = [ "mirror" ],
            system = [ "noiomgr", "iomgr", "mirror" ],
            # system = [ "mirror", "noiomgr" ],
            pktsize = [ 64 ],

            # legacy args
            num_vms = [0],
        )
        test_matrix = measurement.apply_cmdline_overrides(test_matrix)
        tests = PktgenLatencyTest.list_tests(test_matrix)

    tests = deduplicate(tests)
    PktgenLatencyTest.estimate_time2(tests, [])

    if plan_only:
        return

    qemu_pid = None
    pktgen_pid = None

    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for [repetitions, batchsize, workload, memory_workload, chaining, system, pktsize], a_tests in bench.multi_iterator(bench_tests, ["repetitions", "batchsize", "workload", "memory_workload", "chaining", "system", "pktsize"]):
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

    test.pre_initial_cleanup(host, qemu_pid, pktgen_pid)

    dfs = []
    for test in tests:
        for repetition in range(test.repetitions):
            dfs += [ pd.read_csv(test.output_filepath(repetition)) ]
    df = pd.concat(dfs)
    del df['repetition']
    df = df.groupby([ col for col in df.columns if col != "lat_us" ]).describe()
    df.to_csv(path_join(G.OUT_DIR, "vm_lat_summary.csv"))
    with open(path_join(G.OUT_DIR, "vm_lat_summary.log"), 'w') as f:
        f.write(df.to_string())





if __name__ == "__main__":
    measurement = Measurement(test_type=PktgenLatencyTest, supports_boot_only=True)
    main(measurement)
