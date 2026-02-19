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
            with measurement.virtual_machine(Interface.BRIDGE) as guest:
                guest.exec("echo hello world")


                # vhost_sock = "/tmp/vhost0.sock"
                # host.tmux_kill("Pktgen")
                # host.exec(f"sudo rm {vhost_sock} || true")
                # host.tmux_new("Pktgen", f"sudo pktgen -l 6,7,8,9 --vdev 'eth_vhost0,iface={vhost_sock}' -- -m '[0:3].0' -G")

                host.stop_pktgen_vhost()
                host.start_pktgen_vhost()
                sleep(1)
                print(host.exec_pktgen('printf("asdfasdfasdf\\n")'))
                # command = 'printf("Hello from Python!\\n")'
                # script = f"""
                #     package.path = package.path .. ";{host.project_root}/pybench/Pktgen.lua;"
                #     require "Pktgen"
                #     {command}
                # """
                # print(host.exec(f"echo '{script}' | socat - TCP4:localhost:22022"))
                breakpoint()
                pass
            # host.start_vpp()
            # test.compile(host)
            # for repetition in range(test.repetitions):
            #     test.run(host, repetition)
            bench.done(test)

    dfs = []
    for test in tests:
        for repetition in range(test.repetitions):
            dfs += [ test.parse_results(repetition) ]
    df = pd.concat(dfs)
    df.to_csv(path_join(G.OUT_DIR, "userspace_summary.csv"))
    with open(path_join(G.OUT_DIR, "userspace_summary.log"), 'w') as f:
        f.write(df.to_string())





if __name__ == "__main__":
    measurement = Measurement()
    main(measurement)
