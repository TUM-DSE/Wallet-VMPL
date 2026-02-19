from enum import Enum
import netaddr
from pathlib import Path
import ipaddress
import getpass

USERNAME: str = getpass.getuser()

class Machine(Enum):
    # Machine types

    # host machine
    HOST = "host"

    # VM with machine type PC
    PCVM = "pcvm"

    # VM with machine type MicroVM
    MICROVM = "microvm"


class Interface(Enum):
    # Interface types

    # Physical NIC (only works with host machine type)
    PNIC = "pnic"

    # Bridge to physical NIC on host, and for VM additionally VirtIO NIC
    # connected to it via TAP device
    BRIDGE = "bridge"

    # Bridge to physical NIC on host, and for VM additionally VirtIO NIC
    # connected to it via TAP device. Uses linux kernel virtio vhost and
    # overrides other vhost options to on.
    BRIDGE_VHOST = "bridge-vhost"

    # Same as BRIDGE, but with e1000 instead of virtio-net
    BRIDGE_E1000 = "bridge-e1000"

    # MacVTap to physical NIC on host, and for VM additionally VirtIO NIC
    # connected to it
    MACVTAP = "macvtap"

    # VFIO-passthrough to physical NIC for the VM
    VFIO = "vfio"

    # vhost-user device backed by VPP software router
    VPP = "vpp"

    # VMux-passthrough to physical NIC for the VM
    VMUX_PT = "vmux-pt"

    # vMux e1000 emulation to tap backend
    VMUX_EMU = "vmux-emu"

    # vMux e810 emulation to tap backend
    VMUX_EMU_E810 = "vmux-emu-e810"

    # vMux e810 mediation (uses dpdk)
    VMUX_MED = "vmux-med"

    # vMux e1000 emulation to dpdk backend
    VMUX_DPDK = "vmux-dpdk"

    # vMux e810 emulation to dpdk backend
    VMUX_DPDK_E810 = "vmux-dpdk-e810"

    # Pktgen-DPDK using DPDK's builtin vhost-user emulation backend
    PKTGEN_DPDK = "pktgen-dpdk"


    def needs_br_tap(self) -> bool:
        return self in [ Interface.BRIDGE, Interface.BRIDGE_VHOST, Interface.BRIDGE_E1000, Interface.VMUX_EMU, Interface.VMUX_EMU_E810 ]

    def needs_macvtap(self) -> bool:
        return self in [ Interface.MACVTAP ]

    def needs_vfio(self) -> bool: # vfio on the host
        return self in [ Interface.VFIO, Interface.VMUX_PT, Interface.VMUX_DPDK, Interface.VMUX_DPDK_E810, Interface.VMUX_MED, Interface.VPP ]

    def needs_vmux(self) -> bool:
        return self in [ Interface.VMUX_PT, Interface.VMUX_EMU, Interface.VMUX_DPDK, Interface.VMUX_EMU_E810, Interface.VMUX_MED, Interface.VMUX_DPDK_E810 ]

    def needs_vpp(self) -> bool:
        return self in [ Interface.VPP ]

    def is_vhost_user(self) -> bool:
        return self in [ Interface.VPP, Interface.PKTGEN_DPDK ]

    def is_passthrough(self) -> bool:
        return self in [ Interface.VFIO, Interface.VMUX_PT ]

    def is_vhost(self) -> bool:
        return self in [ Interface.BRIDGE_VHOST ]

    def guest_driver(self) -> str:
        if self in [ Interface.VFIO, Interface.VMUX_PT, Interface.VMUX_EMU_E810, Interface.VMUX_MED, Interface.VMUX_DPDK_E810 ]:
            return "ice"
        if self in [ Interface.BRIDGE_E1000, Interface.VMUX_EMU, Interface.VMUX_DPDK ]:
            return "e1000"
        if self in [ Interface.BRIDGE, Interface.BRIDGE_VHOST, Interface.MACVTAP, Interface.VPP, Interface.PKTGEN_DPDK ]:
            return "virtio-net"
        raise Exception(f"Dont know which guest driver is used with {self}")

    @staticmethod
    def choices():
        # return a list of the values of all Enum options
        return [ enum.value for enum in Interface.__members__.values() ]


class Reflector(Enum):
    # Reflector types

    # MoonGen reflector
    MOONGEN = "moongen"

    # XDP reflector
    XDP = "xdp"


class MultiHost:
    """
    Starts from vm_number 1. Vm_number 0 leads to legacy outputs without numbers. -1 returns string matching all numbers.
    """
    @staticmethod
    def range(num_vms: int) -> range:
        return range(1, num_vms + 1)

    @staticmethod
    def ssh_hostname(ssh_hostname: str, vm_number: int):
        if vm_number == 0: return ssh_hostname
        fqdn = ssh_hostname.split(".")
        fqdn[0] = f"{fqdn[0]}{vm_number}"
        return ".".join(fqdn)

    @staticmethod
    def mac(base_mac: str, vm_number: int) -> str:
        if vm_number == 0: return base_mac
        base = netaddr.EUI(base_mac)
        value = base.value + vm_number
        fmt = netaddr.mac_unix
        fmt.word_fmt = "%.2x"
        return str(netaddr.EUI(value).format(fmt))

    @staticmethod
    def ip(base_ip: str, vm_number: int) -> str:
        """
        Increment ips with or without subnets
        """
        ip = base_ip.split("/") # split subnet mask
        start = ipaddress.IPv4Address(ip[0])
        if len(ip) == 1:
            return f"{start + vm_number - 1}"
        else:
            # re-attach subnet
            return f"{start + vm_number - 1}/{ip[1]}"

    @staticmethod
    def generic_path(path_: str, vm_number: int) -> str:
        if vm_number == 0: return path_
        path = Path(path_)
        path = path.with_name(path.stem + str(vm_number) + path.suffix)
        return str(path)

    @staticmethod
    def disk_path(root_disk_file: str, vm_number: int) -> str:
        return MultiHost.generic_path(root_disk_file, vm_number)

    @staticmethod
    def vfu_path(vfio_user_socket_path: str, vm_number: int) -> str:
        return MultiHost.generic_path(vfio_user_socket_path, vm_number)

    @staticmethod
    def cloud_init(disk_path: str, vm_number: int) -> str:
        init_disk = Path(disk_path).resolve()
        init_disk = init_disk.parent / f"cloud-init/vm{vm_number}.img"
        return str(init_disk)

    @staticmethod
    def iface_name(tap_name: str, vm_number: int):
        """
        kernel interface name
        """
        if vm_number == 0: return tap_name
        max_len = 15
        length = max_len - len("-999")
        if vm_number == -1: return f"{tap_name[:length]}-"
        return f"{tap_name[:length]}-{vm_number}"

    @staticmethod
    def vhost_user_sock(vm_number: int):
        return f"/tmp/vhost-user-{USERNAME}.{vm_number}"

    @staticmethod
    def enumerate(enumeratable: str, vm_number: int) -> str:
        if vm_number == 0: return enumeratable
        return f"{enumeratable}-vm{vm_number}"


