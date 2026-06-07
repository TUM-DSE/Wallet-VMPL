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
from subprocess import CalledProcessError

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
        PktgenTest.containers_cleanup(host)
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

    def containers_kni_setup(self, guest: Guest):
        nic = guest.test_iface
        n = self.chaining
        # Create veth pairs: veth{i}a (host-side, for TC chaining) <-> veth{i}b (container-side, for AF_PACKET)
        for i in range(n):
            guest.exec(f"sudo ip link add veth{i}a type veth peer name veth{i}b")
            guest.exec(f"sudo ip link set veth{i}a up")
            guest.exec(f"sudo ip link set veth{i}b up")
        # NIC ingress → first veth pair
        guest.exec(f"sudo tc qdisc add dev {nic} ingress")
        guest.exec(f"sudo tc filter add dev {nic} ingress protocol all u32 match u32 0 0 action mirred egress redirect dev veth0a")
        # Chain: veth_i_a ingress → veth_(i+1)_a egress
        for i in range(n - 1):
            guest.exec(f"sudo tc qdisc add dev veth{i}a ingress")
            guest.exec(f"sudo tc filter add dev veth{i}a ingress protocol all u32 match u32 0 0 action mirred egress redirect dev veth{i+1}a")
        # Last veth ingress → NIC TX
        guest.exec(f"sudo tc qdisc add dev veth{n-1}a ingress")
        guest.exec(f"sudo tc filter add dev veth{n-1}a ingress protocol all u32 match u32 0 0 action mirred egress redirect dev {nic}")

    def kata_kni_setup(self, guest: Guest):
        """Sets up veth chain with bridges for kata containers, plus a pktgen veth pair.
        Kata containers run in VMs, so they can't use AF_PACKET directly. Instead,
        each veth{i}b is attached to a bridge, and a docker network is created for
        that bridge. The kata VM gets a virtio-net NIC connected to the bridge.
        Returns the pktgen interface name (for af_packet)."""
        n = self.chaining
        # Pktgen veth pair: pktgen sends/receives on pktgen_out, TC chain attaches to pktgen_in
        guest.exec(f"sudo ip link add pktgen_in type veth peer name pktgen_out")
        guest.exec(f"sudo ip link set pktgen_in up")
        guest.exec(f"sudo ip link set pktgen_out up")
        # Create chain veth pairs + bridges
        for i in range(n):
            guest.exec(f"sudo ip link add veth{i}a type veth peer name veth{i}b")
            guest.exec(f"sudo ip link set veth{i}a up")
            guest.exec(f"sudo ip link set veth{i}b up")
            guest.exec(f"docker network create --driver=bridge "
                       f"--opt com.docker.network.bridge.name=br-vnf{i} "
                       f"--subnet=172.30.{i}.0/30 "
                       f"vnf{i}-net")
            guest.exec(f"sudo brctl addif br-vnf{i} veth{i}b")
        # TC: pktgen_in ingress → first veth pair
        guest.exec(f"sudo tc qdisc add dev pktgen_in ingress")
        guest.exec(f"sudo tc filter add dev pktgen_in ingress protocol all u32 match u32 0 0 action mirred egress redirect dev veth0a")
        # Chain: veth_i_a ingress → veth_(i+1)_a egress
        for i in range(n - 1):
            guest.exec(f"sudo tc qdisc add dev veth{i}a ingress")
            guest.exec(f"sudo tc filter add dev veth{i}a ingress protocol all u32 match u32 0 0 action mirred egress redirect dev veth{i+1}a")
        # Last veth ingress → pktgen_in (completes the loop)
        guest.exec(f"sudo tc qdisc add dev veth{n-1}a ingress")
        guest.exec(f"sudo tc filter add dev veth{n-1}a ingress protocol all u32 match u32 0 0 action mirred egress redirect dev pktgen_in")
        return "pktgen_out"

    @staticmethod
    def containers_cleanup(guest: Guest):
        nic = guest.test_iface
        # Stop all possible mirror containers from previous runs
        guest.exec("docker kill mirror{0..64} 2>/dev/null || true")
        guest.exec("docker rm -f $(docker ps -aq --filter name=mirror{0..64}) 2>/dev/null || true")
        guest.tmux_kill(f"workload*") # i dont think this wildcard is actually applied by the underlying grep
        # Remove docker networks and bridges created for kata
        guest.exec("for i in $(seq 0 63); do docker network rm vnf${i}-net 2>/dev/null; done; true")
        # Delete pktgen veth pair
        guest.exec("sudo ip link del pktgen_in 2>/dev/null || true")
        # Delete all possible veth pairs (deleting the a-side removes both ends)
        guest.exec("for i in $(seq 0 63); do sudo ip link del veth${i}a 2>/dev/null; done; true")
        guest.exec(f"sudo tc qdisc del dev {nic} ingress 2>/dev/null || true")

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
        ) + (
            # tie the loadgen measurement duration to the framework's
            [ f"-DRUNTIME_S={int(G.DURATION_S)}" ] if self.system == "iomgrMicrobenchmark" else []
        ))

        trustlets = []
        dpdk_examples = []
        runners = []
        if self.system in [ "mirror", "containers", "kata", "mirrorUnconfidential", "mirrorKni", "mirrorMicrobenchmark", "mirrorKniMicrobenchmark" ]:
            dpdk_examples = ["mirror"]
        elif self.system == "noiomgr":
            trustlets = ["noiomgr_trustlet"]
            runners = ["noiomgr_run"]
        elif self.system in [ "iomgr", "iomgrMicrobenchmark" ]:
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
        # if self.chaining == 1 and "mirror" not in self.system:
        #     raise NotImplementedError("Chaining == 1 not implemented")

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

        guest.exec("rm -f /tmp/.dpdk-running || true")
        time_start = datetime.now()
        if self.system in [ "mirror", "mirrorUnconfidential" ]:
            guest.tmux_new("workload", f"./module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa {dpdk_mbuf_pool_type}; sleep 999") # | tee {remote_mirror_output}")
        elif self.system == "mirrorKni":
            tap_vdev = f"--no-pci --vdev=net_af_packet0,iface={guest.test_iface}"
            guest.tmux_new("workload", f"./module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa {tap_vdev} {dpdk_mbuf_pool_type}; sleep 999") # | tee {remote_mirror_output}")
        elif self.system == "mirrorMicrobenchmark":
            guest.tmux_new("workload", "sudo ./module/example-dpdk/mirror -l 2 --no-huge --iova-mode=pa --mbuf-pool-ops-name='stack' --no-pci --vdev 'eth_vhost0,iface=/tmp/vhost-user-okelmann.loadgen' --file-prefix 'foo'")
            guest.exec("echo 1024 | sudo tee /sys/devices/system/node/node0/hugepages/hugepages-2048kB/nr_hugepages")
            pktgen_bin = f"{guest.project_root}/.nix-builds/pktgen-dpdk/bin"
            guest.tmux_new("workload2", f"sudo {pktgen_bin}/pktgen --vdev 'net_virtio_user0,path=/tmp/vhost-user-okelmann.loadgen,speed=100000' --single-file-segments -l0,1 --no-pci -- -m '1.0' -G")
            for i in range(10):
                try:
                    if guest.exec_pktgen('printf("PKTGEN_UP")') == "PKTGEN_UP":
                        break
                except CalledProcessError:
                    pass
                if i >= 9:
                    raise RuntimeError("Pktgen did not start in time")
                sleep(1)
        elif self.system == "mirrorKniMicrobenchmark":
            # like mirrorMicrobenchmark, but pktgen and mirror are connected
            # through linux networking (veth pair + AF_PACKET) instead of vhost-user
            guest.exec("sudo ip link del mb_kni_a 2>/dev/null || true")
            guest.exec("sudo ip link add mb_kni_a type veth peer name mb_kni_b")
            guest.exec("sudo ip link set mb_kni_a up")
            guest.exec("sudo ip link set mb_kni_b up")
            guest.tmux_new("workload", "sudo ./module/example-dpdk/mirror -l 2 --no-huge --iova-mode=pa --mbuf-pool-ops-name='stack' --no-pci --vdev=net_af_packet0,iface=mb_kni_b --file-prefix 'foo'")
            guest.exec("echo 1024 | sudo tee /sys/devices/system/node/node0/hugepages/hugepages-2048kB/nr_hugepages")
            pktgen_bin = f"{guest.project_root}/.nix-builds/pktgen-dpdk/bin"
            guest.tmux_new("workload2", f"sudo {pktgen_bin}/pktgen --no-pci --vdev=net_af_packet0,iface=mb_kni_a -l0,1 -- -m '1.0' -G")
            for i in range(10):
                try:
                    if guest.exec_pktgen('printf("PKTGEN_UP")') == "PKTGEN_UP":
                        break
                except CalledProcessError:
                    pass
                if i >= 9:
                    raise RuntimeError("Pktgen did not start in time")
                sleep(1)
        elif self.system == "containers":
            PktgenTest.containers_cleanup(guest)
            self.containers_kni_setup(guest)
            for i in range(self.chaining):
            # for i in range(1):
                tap_vdev = f"--no-pci --vdev=net_af_packet0,iface=veth{i}b"
                guest.tmux_new(f"workload{i}",
                    f"docker run --rm --name mirror{i} "
                    f"--network=host --privileged -v /:/host "
                    f"busybox chroot /host "
                    f"/root/module/example-dpdk/mirror -l 0 --no-huge --iova-mode=pa --file-prefix=mirror{i} {tap_vdev} {dpdk_mbuf_pool_type}; sleep 999" # TODO : cpu pinning
                )
        elif self.system == "kata":
            # linux networking has already been set up previously for pktgen to connect
            for i in range(self.chaining):
                tap_vdev = f"--no-pci --vdev=net_af_packet0,iface=eth0"
                guest.tmux_new(f"workload{i}",
                    f"docker run --rm --name mirror{i} "
                    f"--runtime kata-qemu-slick "
                    f"--network=vnf{i}-net "
                    # f"--privileged" # faults with EEXIST: File exists on kata
                    f"--cap-add=NET_ADMIN --cap-add=NET_RAW "
                    f"-v /nix:/nix "
                    f"-v /tmp:/tmp "
                    f"-v {host.project_root}:{host.project_root} "
                    f"busybox sh -c '"
                    f"mkdir -p /var/run && "
                    f"{host.project_root}/module/example-dpdk/mirror -l 0 --no-huge --file-prefix=mirror{i} {tap_vdev} {dpdk_mbuf_pool_type}; sleep 999'" # --iova-mode=pa is unavailable in kata container # TODO : cpu pinning
                )
        elif self.system == "noiomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./noiomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        elif self.system == "iomgr":
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./iomgr_run -l 0 --no-huge --iova-mode=pa") # | tee {remote_mirror_output}")
        elif self.system == "iomgrMicrobenchmark":
            remote_out = "/tmp/iomgr_microbenchmark.out"
            guest.exec(f"rm {remote_out} || true")
            guest.tmux_new("workload", f"cd ./module/example-dpdk; ./iomgr_run -l 0 --no-huge --iova-mode=pa --loadgen; sleep 999") # | tee {remote_mirror_output}")
            # trustlet setup takes up to ~80s; /tmp/.dpdk-running marks the measurement start
            guest.wait_for_success("test -f /tmp/.dpdk-running", timeout=90*max(self.num_vms, self.chaining))
            # iomgr_run measures for RUNTIME_S (== G.DURATION_S, injected at compile time), then writes the result
            guest.wait_for_success(f"test -f {remote_out}", timeout=G.DURATION_S + 60)

            pps = []
            pkt_counts = [0, 0]
            for line in guest.exec(f"cat {remote_out}").splitlines():
                parts = line.split()
                if len(parts) != 2:
                    continue
                if parts[0] == "pps":
                    pps += [ float(parts[1]) ]
                elif parts[0] == "tx_packets":
                    pkt_counts[0] = int(parts[1])
                elif parts[0] == "rx_packets":
                    pkt_counts[1] = int(parts[1])

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
        if self.system == "kata":
            # Docker enables hairpin on its bridge ports, causing mirror responses
            # to loop back to the same mirror infinitely. Wait for kata veths to
            # appear (bridge gets 2+ ports), then disable hairpin on all ports.
            # Must happen before mirror starts processing packets.
            for i in range(self.chaining):
                guest.wait_for_success(f"test $(ls /sys/class/net/br-vnf{i}/brif/ | wc -l) -ge 2", timeout=60)
                guest.exec(f"for port in $(ls /sys/class/net/br-vnf{i}/brif/); do sudo sh -c 'echo 0 > /sys/class/net/br-vnf{i}/brif/'$port'/hairpin_mode'; done")
        guest.wait_for_success("test -f /tmp/.dpdk-running", timeout=90*max(self.num_vms, self.chaining)) # with long chains, we have to expect up to 80s per VNFlet
        time_end = datetime.now()
        print(f"Slick start time: {(time_end - time_start).total_seconds():.2f} seconds")


    def measure(self, host: Server, guest: Server, repetition: int):
        if self.system == "iomgrMicrobenchmark":
            return None
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
        if self.system in [ "containers", "kata", "mirrorKni", "mirrorKniMicrobenchmark" ]:
            # container throughput collapses at excessive offered traffic rates
            # host.exec_pktgen(f'pktgen.set("all", "rate", 2)') # @1500B: 164kpps offered -> 95kpps
            # host.exec_pktgen(f'pktgen.set("all", "rate", 0.12)') # @64B: 178kpps offered -> 96kpps
            target_pps = 164000 if self.system in [ "containers", "mirrorKni", "mirrorKniMicrobenchmark" ] else 1000000
            rate_pct = target_pps * (self.pktsize + 20) * 8 / 10e9 * 10
            host.exec_pktgen(f'pktgen.set("all", "rate", {rate_pct:.2f})')
        host.exec_pktgen('pktgen.start(0)')
        time_start = datetime.now()
        sleep(3)
        pps = []
        for _ in range(G.DURATION_S):
            lua = """
                printf(pktgen.portStats("0", "rate")[0].pkts_rx)
            """
            pps += [ int(host.exec_pktgen(lua)) ]
            sleep(1)
        host.exec_pktgen('pktgen.stop(0)')
        time_stop = datetime.now()

        pkt_counts = host.exec_pktgen('printf(pktgen.portStats("0", "port")[0].opackets .. "/" .. pktgen.portStats("0", "port")[0].ipackets)').split("/")

        # if self.system == "kata": # pktgen rate report is broken with kernel interfaces
        #     measurement_duration = (time_stop - time_start).total_seconds()
        #     avg_pps = float(pkt_counts[1]) / measurement_duration
        #     pps = [ avg_pps for _ in pps ]

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
        system = [ "iomgr", "noiomgr", "insecure", "containers", "kata" ],
        pktsize = [ 64, 1500 ],

        # legacy args
        num_vms = [0],
    )
    workload_tests_64b = dict(
        workload = [ 0, 1, 5, 10, 20, 40, 80, 160, 320, 640, 1280 ],
        system = [ "iomgr", "noiomgr", "insecure", "containers", "kata" ],
        pktsize = [ 64 ],
        real_workload = [ "synthetic" ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], chaining = [2], num_vms = [0],
    )
    workload_tests_1500b = dict(
        workload = [ int(i) for i in np.linspace(0, 2000, 10) ],
        system = [ "iomgr", "noiomgr", "insecure", "containers", "kata" ],
        pktsize = [ 1500 ],
        real_workload = [ "synthetic" ], memory_workload = [ 0 ], repetitions=[2], batchsize = [32], chaining = [2], num_vms = [0],
    )
    memory_workload_tests = dict(
        memory_workload = [ int(i) for i in np.linspace(0, 0x1000, 10) ],
        system = [ "iomgr", "noiomgr", "insecure", "containers", "kata" ],
        pktsize = [ 64, 1500 ],
        real_workload = [ "synthetic" ], workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], chaining = [2], num_vms = [0],
    )
    chaining_tests = dict(
        system = [ "iomgr", "noiomgr", "insecure", "containers", "kata" ],
        pktsize = [ 64, 1500 ],
        chaining = [2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 32],
        real_workload = [ "synthetic" ], workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], num_vms = [0],
    )
    real_workload_tests = dict(
        system = [ "iomgr", "noiomgr", "insecure", "containers", "kata" ],
        pktsize = [ 64, 128, 256, 512, 1024, 1500 ],
        real_workload = [ "real" ],
        chaining = [ 3 ], workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], num_vms = [0],
    )
    ioengine_tests = dict(
        system = [ "iomgr", "containers", "kata", "mirror", "mirrorUnconfidential", "mirrorKni", "mirrorMicrobenchmark", "mirrorKniMicrobenchmark" ],
        pktsize = [ 64, 128, 256, 512, 1024, 1500 ],
        chaining = [ 1 ],
        real_workload = [ "synthetic", "real" ],
        workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], batchsize = [32], num_vms = [0],
    )
    vnfletio_tests = dict(
        system = [ "mirrorMicrobenchmark", "mirrorKniMicrobenchmark" ],
        pktsize = [ 64, 128, 256, 512, 1024, 1500 ],
        chaining = [ 1 ],
        real_workload = [ "synthetic", "real" ],
        batchsize = [ 1, 32 ],
        workload = [ 0 ], memory_workload = [ 0 ], repetitions=[REPETITIONS], num_vms = [0],
    )
    if mode != "latency":
        vnfletio_tests["system"] += [ "iomgrMicrobenchmark" ]
    tests = \
        PktgenTest.list_tests(basic_tests) + \
        PktgenTest.list_tests(workload_tests_64b) + \
        PktgenTest.list_tests(workload_tests_1500b) + \
        PktgenTest.list_tests(memory_workload_tests) + \
        PktgenTest.list_tests(chaining_tests) + \
        (PktgenTest.list_tests(real_workload_tests) if mode != "latency" else []) + \
        PktgenTest.list_tests(ioengine_tests) + \
        PktgenTest.list_tests(vnfletio_tests)


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
                if test.system == "kata":
                    PktgenTest.containers_cleanup(host)
                    test.kata_kni_setup(host)
                    host.start_pktgen_kni("pktgen_out")
                else:
                    host.start_pktgen_vhost()
                pktgen_pid = host.tmux_get_pid("pktgen")
                with open(f"/tmp/pidfile.{getpass.getuser()}.pktgen", "w") as f:
                    f.write(str(pktgen_pid))
                # sleep(1) # wait and pray for pktgen
                if test.system == "kata":
                    test.start(host, host, repetition) # what is usually the guest, is now the host
                    test.measure(host, host, repetition) # what is usually the guest, is now the host
                    # breakpoint()
                    pass
                else:
                    confidential = test.system not in [ "mirrorUnconfidential"]
                    with measurement.virtual_machine(Interface.PKTGEN_DPDK, run_guest_args=dict(confidential=confidential)) as guest:
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
                        if test.system in [ "containers", "mirrorKni" ]:
                            guest.exec(f"modprobe {Interface.PKTGEN_DPDK.guest_driver()}")
                            guest.exec(f"{remote_dpdk_path}/bin/dpdk-devbind.py -b {guest.test_iface_driv} {guest.test_iface_addr}")
                            guest.exec(f"ip link set {guest.test_iface} up")
                        else:
                            guest.exec(f"{remote_dpdk_path}/bin/dpdk-devbind.py -b vfio-pci {guest.test_iface_addr} --noiommu-mode")

                        measurement.mark_vm_initialized(0)

                        test.start(host, guest, repetition)
                        if test.system in [ "mirrorMicrobenchmark", "mirrorKniMicrobenchmark" ]:
                            test.measure(guest, guest, repetition)
                        else:
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
