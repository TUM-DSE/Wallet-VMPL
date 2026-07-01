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
import re


def _parse_iperf_serial_gbitps(text: str) -> float:
    """Scrape the iperf3 client's final throughput out of the SVSM serial log
    (the iomgr VNFlet runs iperf inside the trustlet, so its human-readable
    output lands there). Prefer the 'receiver' summary line, fall back to
    'sender'. Returns GBit/s using the same 1024^3 divisor as summarize()."""
    unit_mul = {"": 1.0, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}
    pat = re.compile(r"([\d.]+)\s*([KMGT]?)bits/sec")
    receiver = sender = None
    for line in text.splitlines():
        if "bits/sec" not in line:
            continue
        m = pat.search(line)
        if not m:
            continue
        bps = float(m.group(1)) * unit_mul[m.group(2)]
        if "receiver" in line:
            receiver = bps
        elif "sender" in line:
            sender = bps
    bps = receiver if receiver is not None else sender
    if bps is None:
        raise ValueError("no iperf 'bits/sec' summary line found in serial log")
    return bps / 1024 / 1024 / 1024


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
        sent_bits_per_second = end['sum_sent']['bits_per_second']

        gbitps = max(received_bits_per_second, sent_bits_per_second) / 1024 / 1024 / 1024

        print(f"{gbitps:.2f} GBit/s")

        data = [{
            **asdict(self), # put selfs member variables and values into this dict
            "repetition": repetition,
            "GBit/s": gbitps,
        }]
        return DataFrame(data=data)

    def compile(self, server: Server):
        cflags = " ".join([
            "-DBURST_SIZE=32",
            "-DPACKET_SIZE=1522",
            "-DPER_VNFLET_WORKLOAD_NS=0",
            "-DWORKLOAD_ACCESSES_B=0",
            "-DCHAINING=1",
            "-DIPERF_WORKLOAD=1",
            # f"-DLLC_SIZE={LLC_SIZE}",
        ])

        trustlets = []
        dpdk_examples = []
        runners = []
        if self.system == "iomgr":
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

    def run(self, repetition: int, guest, loadgen, host):
        remote_output_file = "/tmp/iperf.json"
        tmp_remote_output_file = "/tmp/tmp_iperf.json"
        local_json_file = self.output_filepath(repetition, extension="json")
        local_output_file = self.output_filepath(repetition)
        LoadGen.stop_iperf_client(loadgen)
        guest.stop_iperf_server()
        loadgen.exec(f"rm {remote_output_file} {tmp_remote_output_file} | true")

        guest.start_iperf_server(strip_subnet_mask(guest.test_iface_ip_net))
        sleep(10) # without this sleep all systems are at ~10Gbitps
        extra_options = ""
        # extra_options = " -u -P 8 -l 1440 -b 0"
        LoadGen.run_iperf_client(host, G.DURATION_S, strip_subnet_mask(guest.test_iface_ip_net), remote_output_file, tmp_remote_output_file, extra_options=extra_options)
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

    def run_fstack(self, repetition: int, guest, loadgen, host, confidential: bool):
        remote_output_file = "/tmp/iperf.log"
        local_output_file = self.output_filepath(repetition)
        local_output_json = self.output_filepath(repetition, extension="json")
        guest.exec(f"rm {remote_output_file} | true")

        guest.exec("echo 1024 | sudo tee /sys/devices/system/node/node0/hugepages/hugepages-2048kB/nr_hugepages")
        config_name = "config-vhost-c.ini"
        fstack_base_config = f"{host.project_root}/pybench/hosts/{config_name}"
        fstack_config = "/tmp/fstack.conf"
        guest.copy_to(fstack_base_config, fstack_config)

        guest.stop_fstack_iperf()
        extra_options = "-l 1M"
        # extra_options = "-u -P 8 -l 1440 -b 0"
        guest.start_fstack_iperf(fstack_config, f"-c 192.168.31.1 -t {G.DURATION_S} -J {extra_options} | tee {remote_output_file}; echo FINISHED >> {remote_output_file}", confidential=confidential)

        sleep(G.DURATION_S + 3)
        # guest.wait_for_success(f'[[ -e {remote_output_file} ]]', timeout=30)
        guest.wait_for_success(f'grep "FINISHED" {remote_output_file}', timeout=30)
        # sed_str = shlex.quote("'1,/^{$/{/^{$/!d;}'")
        sed_str = "'1,/^{$/{/^{$/!d;}'"
        guest.exec(f"sed -i {sed_str} {remote_output_file}") # remote all lines before the first line starting with {, which is the start of the json output of iperf
        guest.exec(f"sed -i '$d' {remote_output_file}") # remove the last line with FNISHED
        guest.copy_from(remote_output_file, local_output_json)

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

    def run_vnflet(self, host: Server, guest: Server, repetition: int):
        # if self.chaining == 1 and "mirror" not in self.system:
        #     raise NotImplementedError("Chaining == 1 not implemented")

        sleep(1) # for good measure
        local_mirror_output = self.output_filepath(repetition, extension="mirror")
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

        guest.exec("rm -f /tmp/.dpdk-running || true")
        guest.exec("rm /tmp/ipsec_timing.csv || true")
        print("start timer")
        time_start = datetime.now()
        if self.system == "iomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./iomgr_run -l 0 --no-huge --iova-mode=pa 2>&1 | tee {remote_mirror_output}")
        else:
            raise ValueError(f"Unknown system {self.system}")

        # breakpoint()
        # sleep(30)
        # guest.wait_for_success(f"grep 'Core 0 receiving packets.' {remote_mirror_output}", timeout=30)
        guest.wait_for_success("test -f /tmp/.dpdk-running", timeout=300, backoff_sec=0) # with long chains, we have to expect up to 80s per VNFlet

        if self.system in [ "iomgr"]:
            guest.copy_from(remote_mirror_output, local_mirror_output)

        # The iperf client runs *inside* the VNFlet trustlet; its stdout goes to
        # the host's SVSM serial log, not the guest. Wait for the run to finish
        # (marker printed by main_iperf) before the enclosing context tears the VM
        # down, then scrape the throughput and write the per-repetition CSV the
        # summary step reads (otherwise it FileNotFoundErrors on the missing file).
        serial_log = "/tmp/serial.log"
        gbitps = 0.0
        try:
            # serial.log is appended across reboots; wait for a *new* completion
            # marker (count increases) rather than matching a stale one.
            def _marker_count():
                out = host.exec(f"sudo grep -c 'iperf_main returned' {serial_log} || true").strip()
                return int(out) if out.isdigit() else 0
            baseline = _marker_count()
            host.wait_for_success(f"test $(sudo grep -c 'iperf_main returned' {serial_log} || echo 0) -gt {baseline}",
                                  timeout=G.DURATION_S + 60, backoff_sec=1)
            serial_text = host.exec(f"sudo strings {serial_log}")
            gbitps = _parse_iperf_serial_gbitps(serial_text)
            print(f"{gbitps:.2f} GBit/s")
        except Exception as e:
            warning(f"iomgr iperf VNFlet did not finish/print a result: {e}")
            print(traceback.format_exc())

        row = { **asdict(self), "repetition": repetition, "GBit/s": gbitps }
        local_output_file = self.output_filepath(repetition)
        os.makedirs(path_dirname(local_output_file), exist_ok=True)
        DataFrame(data=[row]).to_csv(local_output_file, index=False)


    def pre_initial_cleanup(self, host):
        host.exec("sudo pkill iperf || true")
        host.exec("make kill")
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
        system=[ "vm", "swiotlb", "vhost", "vhost_swiotlb", "snp", "snp_vhost", "poll", "poll_vhost", "haltpoll", "vhost_user" ],
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
        vhost_swiotlb = SimpleNamespace(confidential=False, interface=Interface.BRIDGE_VHOST, iommu_hack=True, linux_cmdline="swiotlb=524288,force"),

        snp = SimpleNamespace(confidential=True, interface=Interface.BRIDGE, iommu_hack=False, linux_cmdline=""),
        snp_vhost = SimpleNamespace(confidential=True, interface=Interface.BRIDGE_VHOST, iommu_hack=False, linux_cmdline=""),
        poll = SimpleNamespace(confidential=True, interface=Interface.BRIDGE, iommu_hack=True, linux_cmdline="idle=poll"),
        poll_vhost = SimpleNamespace(confidential=True, interface=Interface.BRIDGE_VHOST, iommu_hack=True, linux_cmdline="idle=poll"),
        haltpoll = SimpleNamespace(confidential=True, interface=Interface.BRIDGE, iommu_hack=True, linux_cmdline="cpuidle_haltpoll.force=Y"),

        vhost_user = SimpleNamespace(confidential=False, interface=Interface.PKTGEN_DPDK, iommu_hack=True, linux_cmdline="cpuidle_haltpoll.force=Y"),
        iomgr = SimpleNamespace(confidential=True, interface=Interface.PKTGEN_DPDK, iommu_hack=False, linux_cmdline=""),
        vhost_user_slick = SimpleNamespace(confidential=True, interface=Interface.PKTGEN_DPDK, iommu_hack=False, linux_cmdline=""), # broken! Currently crashes the guest kernel
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

                host.stop_fstack_iperf()
                if system_params.interface.is_vhost_user():
                    config_name = "config-vhost-a.ini"
                    fstack_base_config = f"{host.project_root}/pybench/hosts/{config_name}"
                    fstack_config = "/tmp/fstack.conf"
                    host.copy_to(fstack_base_config, fstack_config)

                    host.start_fstack_iperf(fstack_config, "-s -B 192.168.31.1")

                test.compile(host) if test.system == "iomgr" else None

                with measurement.virtual_machine(system_params.interface, run_guest_args=dict(confidential=system_params.confidential,iommu_hack=system_params.iommu_hack)) as guest:

                    guest.exec("modprobe vfio-pci")
                    guest.exec("rmmod module/vmpl.ko || true")
                    guest.exec("insmod module/vmpl.ko")
                    remote_dpdk_path = host.exec(f"realpath {PROJECT_ROOT}/.nix-builds/dpdk").strip()
                    if not system_params.interface.is_vhost_user():
                        guest.modprobe_test_iface_drivers(interface=system_params.interface)
                        guest.setup_test_iface_ip_net()
                    else:
                        guest.exec(f"{remote_dpdk_path}/bin/dpdk-devbind.py -b vfio-pci {guest.test_iface_addr} --noiommu-mode")

                    measurement.mark_vm_initialized(0)

                    if test.system == "iomgr":
                        test.run_vnflet(host, guest, repetition)
                    elif system_params.interface.is_vhost_user():
                        test.run_fstack(repetition, guest, host, host, system_params.confidential)
                    else:
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
    measurement = Measurement(test_type=IperfTest, supports_boot_only=True)
    main(measurement)
