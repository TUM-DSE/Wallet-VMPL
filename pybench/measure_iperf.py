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
        dfs = []
        try:
            dfs += [ self.summarize(repetition) ]
        except Exception as e:
            warning(f"Can't process result of VM repetition {repetition}. Did the benchmark fail?")
            _ignore = traceback.format_exc()
            print(_ignore)
        # to_string preserves all cols
        pd.concat(dfs).to_csv(local_output_file, index=False)

    def pre_initial_cleanup(self, host):
        try:
            host.kill_guest()
        except Exception:
            pass


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
        system=[ "vm", "swiotlb", "vhost", "snp", "snp_vhost", "poll", "haltpoll" ],
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

    # per-device qemu options: ,iommu_platform=on,disable-modern=off,disable-legacy=on
    systems = dict(
        vm = SimpleNamespace(confidential=False, interface=Interface.BRIDGE, iommu_hack=False, linux_cmdline=""),
        swiotlb = SimpleNamespace(confidential=False, interface=Interface.BRIDGE, iommu_hack=True, linux_cmdline="swiotlb=524288,force"),
        vhost = SimpleNamespace(confidential=False, interface=Interface.BRIDGE_VHOST, iommu_hack=False, linux_cmdline=""),

        snp = SimpleNamespace(confidential=True, interface=Interface.BRIDGE, iommu_hack=False, linux_cmdline=""),
        snp_vhost = SimpleNamespace(confidential=True, interface=Interface.BRIDGE_VHOST, iommu_hack=False, linux_cmdline=""),
        poll = SimpleNamespace(confidential=True, interface=Interface.BRIDGE, iommu_hack=True, linux_cmdline="idle=poll"),
        haltpoll = SimpleNamespace(confidential=True, interface=Interface.BRIDGE, iommu_hack=True, linux_cmdline="cpuidle_haltpoll.force=Y"),
    )


    with Bench(tests=tests, args_reboot=[], brief = G.BRIEF) as (bench, bench_tests):
        for _param_dict, a_tests in bench.multi_iterator_dict(bench_tests, test_params):
            assert len(a_tests) == 1 # we have looped through all variables now, right?
            test = a_tests[0]
            info(f"Running {test}")
            for repetition in range(test.repetitions):
                system_params = systems[test.system]
                test.pre_initial_cleanup(host)

                # change the linux boot params of the guest grub installation
                extra_linux_cmdline = system_params.linux_cmdline
                # /etc/default/grub is sourced as shell by grub-mkconfig, so the value needs its own quoting layer
                grub_line = "GRUB_CMDLINE_LINUX_EXTRA=" + shlex.quote(extra_linux_cmdline)
                sed_replacement = grub_line.replace("\\", "\\\\").replace("&", "\\&").replace("|", "\\|")
                sed_cmd = f"sed -i {shlex.quote(f's|GRUB_CMDLINE_LINUX_EXTRA=.*|{sed_replacement}|')} /etc/default/grub"
                host.exec(f"virt-customize --format qcow2 -a {host.guest_root_disk_path} --run-command {shlex.quote(sed_cmd)} --run-command 'grub-mkconfig -o /boot/grub/grub.cfg'")

                with measurement.virtual_machine(system_params.interface, run_guest_args=dict(confidential=system_params.confidential,iommu_hack=system_params.iommu_hack)) as guest:
                    guest.modprobe_test_iface_drivers(interface=system_params.interface)
                    guest.setup_test_iface_ip_net()
                    test.run(repetition, guest, host, host)
            bench.done(test)

    dfs = []
    for test in tests:
        for repetition in range(test.repetitions):
            dfs += [ pd.read_csv(test.output_filepath(repetition)) ]
    df = pd.concat(dfs)
    del df['repetition']
    df = df.groupby([ col for col in df.columns if col != "GBit/s" ]).describe()
    df.to_csv(path_join(G.OUT_DIR, f"iperf_summary.csv"))
    with open(path_join(G.OUT_DIR, f"iperf_summary.log"), 'w') as f:
        f.write(df.to_string())

if __name__ == "__main__":
    measurement = Measurement(test_type=IperfTest)
    main(measurement)
