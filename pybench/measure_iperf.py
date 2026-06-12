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

@dataclass
class IperfTest(AbstractBenchTest):
    system: str
    direction: str

    def test_infix(self):
        return f"iperf_{self.system}_{self.direction}"

    def estimated_runtime(self):
        return G.DURATION_S

    def find_error(self, repetition: int) -> bool:
        failure = False
        if not self.output_json:
            file = self.output_filepath(repetition)
            if os.stat(file).st_size == 0:
                error(f"Some iperf tests returned errors:\n{file}")
                failure = True
        return failure

    def summarize(self, repetition: int) -> DataFrame:
        with open(self.output_filepath(repetition, extension="json"), 'r') as f:
            data = json.load(f)

        # Extract important values
        start = data['start']
        end = data['end']
        intervals = data['intervals']

        duration_secs = end['sum_sent']['seconds']
        sent_bytes = end['sum_sent']['bytes']
        sent_bits_per_second = end['sum_sent']['bits_per_second']
        received_bytes = end['sum_received']['bytes']
        received_bits_per_second = end['sum_received']['bits_per_second']

        gbitps = received_bits_per_second / 1024 / 1024 / 1024

        data = [{
            **asdict(self), # put selfs member variables and values into this dict
            "repetition": repetition,
            "GBit/s": gbitps,
        }]
        return DataFrame(data=data)


    def run(self, repetition: int, guest, loadgen, host):
        remote_output_file = "/tmp/iperf.json"
        tmp_remote_output_file = "/tmp/tmp_iperf.json"
        local_json_file = self.output_filepath(repetition, extension="json")
        local_output_file = self.output_filepath(repetition)
        LoadGen.stop_iperf_client(loadgen)
        guest.stop_iperf_server()
        loadgen.exec(f"rm {remote_output_file} {tmp_remote_output_file} | true")

        guest.start_iperf_server(strip_subnet_mask(guest.test_iface_ip_net))
        # sleep(10)
        LoadGen.run_iperf_client(host, G.DURATION_S, strip_subnet_mask(guest.test_iface_ip_net), remote_output_file, tmp_remote_output_file)
        sleep(G.DURATION_S)
        loadgen.wait_for_success(f'[[ -e {remote_output_file} ]]', timeout=30)
        loadgen.exec(f'mkdir -p {path_dirname(local_output_file)} || true')
        loadgen.exec(f"cp {remote_output_file} {local_json_file}")


        guest.stop_iperf_server()
        LoadGen.stop_iperf_client(loadgen)

        # summarize results of VM
        with open(local_output_file, 'w') as file:
            dfs = []
            try:
                dfs += [ self.summarize(repetition) ]
            except Exception as e:
                warning(f"Can't process result of VM repetition {repetition}. Did the benchmark fail?")
                _ignore = traceback.format_exc()
                print(_ignore)
            # to_string preserves all cols
            if len(dfs) > 0:
                summary = pd.concat(dfs).to_string()
            else:
                summary = "no results"
            file.write(summary)


def main(measurement, plan_only: bool = False):
    pass

    host, loadgen = measurement.hosts()
    tests : List[IperfTest] = []
    G.DURATION_S = 15
    REPETITIONS = 2
    if measurement.args.extremes_only:
        G.DURATION_S = 5
        REPETITIONS = 1

    basic_tests = dict(
        repetitions=[REPETITIONS],
        system=[ "snp", "vm", "vhost", "snp_vhost" ],
        direction=[ "forward" ],
        num_vms = [ 0 ], # legacy arg
    )
    tests = IperfTest.list_tests(basic_tests)

    if G.BRIEF:
        G.DURATION_S = 5
        REPETITIONS = 1
        test_matrix = dict(
            repetitions=[REPETITIONS],
            system=[ "snp" ],
            direction=[ "forward" ],
            num_vms = [ 0 ], # legacy arg
        )
        test_matrix = measurement.apply_cmdline_overrides(test_matrix)
        tests = IperfTest.list_tests(test_matrix)

    tests = deduplicate(tests)
    test_params = ["repetitions", "num_vms", "system", "direction"] #  define iteration order
    assert sorted(test_params) == sorted(IperfTest.test_parameters())

    if measurement.args.extremes_only:
        tests = IperfTest.filter_extremes(tests, test_params)

    IperfTest.estimate_time2(tests, [])

    if plan_only:
        return

    systems = dict(
        vm = SimpleNamespace(confidential=False, interface=Interface.BRIDGE),
        snp = SimpleNamespace(confidential=True, interface=Interface.BRIDGE),
        vhost = SimpleNamespace(confidential=False, interface=Interface.BRIDGE_VHOST),
        snp_vhost = SimpleNamespace(confidential=True, interface=Interface.BRIDGE_VHOST),
    )


    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for _param_dict, a_tests in bench.multi_iterator_dict(bench_tests, test_params):
            assert len(a_tests) == 1 # we have looped through all variables now, right?
            test = a_tests[0]
            info(f"Running {test}")
            for repetition in range(test.repetitions):
                system_params = systems[test.system]
                with measurement.virtual_machine(system_params.interface, run_guest_args=dict(confidential=system_params.confidential)) as guest:
                    guest.modprobe_test_iface_drivers(interface=system_params.interface)
                    guest.setup_test_iface_ip_net()
                    test.run(repetition, guest, host, host)
            bench.done(test)

if __name__ == "__main__":
    measurement = Measurement(test_type=IperfTest)
    main(measurement)
