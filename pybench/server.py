from dataclasses import dataclass, field
from subprocess import check_output, CalledProcessError, STDOUT
from socket import getfqdn
from logging import debug, info, warning, error
from time import sleep
from datetime import datetime
from abc import ABC
from os import listdir, remove
from os.path import join as path_join
from os.path import dirname as path_dirname
from typing import Optional, List, Dict, Type
from enums import Interface, MultiHost
from pathlib import Path
from util import strip_subnet_mask
import copy
import base64
import cpupinning
import json

BRIDGE_QUEUES: int = 0; # legacy default: 4
MAX_VMS: int = 35; # maximum number of VMs expected (usually for cleanup functions that dont know what to clean up)


@dataclass
class Server(ABC):
    """
    Server class.

    This class represents a server.

    Attributes
    ----------
    fqdn : str
        The fully qualified domain name of the server.
    localhost : bool
        True if the server is localhost.
    nixos : bool
        True if the server is running NixOS.
    test_iface : str
        The name of the interface to test.
    test_iface_addr : str
        The PCI bus address of the interface to test.
    test_iface_driv : str
        The default driver of the interface to test.
    test_iface_dpdk_driv : str
        The DPDK driver of the interface to test.
    test_iface_mac : str
        The MAC address of the interface to test.
    tmux_socket : str
        The name for the tmux socket.
    moongen_dir : str
        The directory of the MoonGen installation.
    moonprogs_dir : str
        The directory with the MoonGen Lua programs.
    xdp_reflector_dir : str
        The directory of the XDP reflector installation.
    localhost : bool
        True if the server is localhost.

    Methods
    -------
    __init__ : Initialize the object.
    __post_init__ : Post initialization.
    is_reachable : Check if the server is reachable.
    __exec_local : Execute a command on the localhost.
    __exec_ssh : Execute a command on the server over SSH.
    exec : Execute command on the server.
    tmux_new : Start a tmux session on the server.
    tmux_kill : Stop a tmux session on the server.
    tmux_send_keys : Send keys to a tmux session on the server.
    __copy_local : Copy a file to the localhost.
    __scp_to : Copy a file to the server.
    __scp_from : Copy a file from the server.
    copy_to : Copy a file to the server.
    copy_from : Copy a file from the server.

    See Also
    --------

    Examples
    --------
    >>> Server('server.test.de')
    Server(fqdn='server.test.de')
    """
    fqdn: str
    test_iface: str
    test_iface_addr: str
    _test_iface_id: int = field(default=None, init=False)
    test_iface_mac: str
    test_iface_driv: str
    test_iface_dpdk_driv: str
    tmux_socket: str
    moongen_dir: str
    project_root: str
    xdp_reflector_dir: str
    cpupinner: cpupinning.CpuPinner = cpupinning.CpuPinner(None)
    localhost: bool = False
    nixos: bool = False
    ssh_config: Optional[str] = None
    ssh_as_root: bool = False

    def __post_init__(self: 'Server') -> None:
        """
        Post initialization.

        This method is called after the object is created.

        Parameters
        ----------

        Returns
        -------

        See Also
        --------
        __init__ : Initialize the object.
        """
        self.nixos = True # all hosts are nixos actually
        self.cpupinner = cpupinning.CpuPinner(self)
        self.localhost = self.fqdn == 'localhost' or self.fqdn == getfqdn()
        return
        try:
            self.nixos = self.isfile('/etc/NIXOS')
        except Exception:
            warning(f'Could not run nixos detection on {self.fqdn}')

    def log_name(self: 'Server') -> str:
        """
        Get the log name.

        Parameters
        ----------

        Returns
        -------
        str
            The log name.
        """
        return f'{self.__class__.__name__.lower()} {self.fqdn}'

    def is_reachable(self: 'Server') -> bool:
        """
        Check if the server is reachable.

        Parameters
        ----------

        Returns
        -------
        bool
            True if the server is reachable.

        See Also
        --------
        exec : Execute command on the server.
        """
        if self.localhost:
            return True
        else:
            try:
                check_output(f'ping -c 1 -W 1 {self.fqdn}', shell=True)
            except CalledProcessError:
                return False
            else:
                return True

    def __cmd_with_package(self: 'Server', package: str) -> str:
        """
        Returns a prefix for a console command. The prefix ensures package to be available to command.
        Command will not run in a shell!
        """
        return f"nix shell --inputs-from {self.project_root} nixpkgs#{package} --command"

    def __exec_local(self: 'Server', command: str) -> str:
        """
        Execute a command on the localhost.

        This method is called by the exec method if the server is localhost.

        Parameters
        ----------
        command : str
            The command to execute.

        Returns
        -------
        str
            The output of the command.

        See Also
        --------
        exec : Execute command on the server.
        __exec_ssh : Execute a command on the server over SSH.
        """
        return check_output(command, stderr=STDOUT, shell=True).decode('utf-8')

    def __exec_ssh(self: 'Server', command: str) -> str:
        """
        Execute a command on the server over SSH.

        This method is called by the exec method if the server is not
        localhost.

        Parameters
        ----------
        command : str
            The command to execute.

        Returns
        -------
        str
            The output of the command.

        See Also
        --------
        exec : Execute command on the server.
        __exec_local : Execute a command on the localhost.
        """
        argv = []
        if self.ssh_as_root == True:
            argv += ["sudo"]
        argv += ["ssh"]
        if self.ssh_config is not None:
            argv += ["-F", f"{self.ssh_config}"]
        argv += [self.fqdn, command]

        return check_output(argv, stderr=STDOUT).decode('utf-8')

    def exec(self: 'Server', command: str, echo: bool = True) -> str:
        """
        Execute command on the server.

        If the server is not localhost the command is executed over SSH.

        Parameters
        ----------
        command : str
            The command to execute.

        Returns
        -------
        str
            The output of the command.

        See Also
        --------
        __exec_local : Execute a command on the localhost.
        __exec_ssh : Execute a command on the server over SSH.

        Example
        -------
        >>> print(server.exec('ls -l'))
        .bashrc
        """
        if echo: debug(f'Executing command on {self.log_name()}: {command}')

        if self.localhost:
            return self.__exec_local(command)
        else:
            return self.__exec_ssh(command)

    def write(self: 'Server', content: str | bytes, path: str, verbose: bool = False) -> None:
        if verbose:
            debug(f'Executing command on {self.log_name()}: Writing to file {path} the following:\n{content}')
        else:
            debug(f'Executing command on {self.log_name()}: Writing to file {path}')
        # encode so we dont have to fuck aroudn with quotes (they get removed somewhere)
        if isinstance(content, str):
            content = bytes(content, 'utf-8')
        b64 = base64.b64encode(content).decode("utf-8")
        self.exec(f"echo {b64} | base64 -d > {path}", echo=False)

    def whoami(self: 'Server') -> str:
        """
        Get the user name.

        Parameters
        ----------

        Returns
        -------
        str
            The user name.
        """
        return self.exec('whoami').strip()

    def gethome(self: 'Server') -> str:
        """
        Get the home directory.

        Parameters
        ----------

        Returns
        -------
        str
            The home directory.
        """
        return self.exec('echo $HOME').strip()

    def isfile(self: 'Server', path: str) -> bool:
        """
        Check if a file exists.

        Parameters
        ----------
        path : str
            The path to the file.

        Returns
        -------
        bool
            True if the file exists.
        """
        return self.exec(f'test -f {path} && echo true || echo false'
                         ).strip() == 'true'

    def isdir(self: 'Server', path: str) -> bool:
        """
        Check if a directory exists.

        Parameters
        ----------
        path : str
            The path to the directory.

        Returns
        -------
        bool
            True if the directory exists.
        """
        return self.exec(f'test -d {path} && echo true || echo false'
                         ).strip() == 'true'

    def check_cpu_freq(self: 'Server') -> None:
        """
        Throw if cpufreq is wrong
        """
        intel_path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
        intel_powersave = "/sys/devices/system/cpu/intel_pstate/min_perf_pct"
        amd_path = "/sys/devices/system/cpu/cpufreq/boost" # every other CPU
        if (self.isfile(intel_path)):
            try:
                self.exec(f"[[ $(cat {intel_path}) -eq 1 ]]")
            except CalledProcessError:
                error(f"Please run on {self.fqdn}: echo 1 | sudo tee {intel_path}")
                raise Exception(f"Wrong CPU freqency on {self.fqdn}")
        if (self.isfile(intel_powersave)):
            try:
                self.exec(f"[[ $(cat {intel_powersave}) -eq 100 ]]")
            except CalledProcessError:
                error(f"Please run on {self.fqdn}: echo 100 | sudo tee {intel_powersave}")
                raise Exception(f"Wrong CPU freqency on {self.fqdn}")
        if (self.isfile(amd_path)):
            try:
                self.exec(f"[[ $(cat {amd_path}) -eq 0 ]]")
            except CalledProcessError:
                error(f"Please run on {self.fqdn}: echo 0 | sudo tee {amd_path}")
                raise Exception(f"Wrong CPU freqency on {self.fqdn}")
            # maybe also cat /sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq | sudo tee /sys/devices/system/cpu/cpufreq/policy*/scaling_min_freq
            # but my cpu still scales down a bit (under load i think)



    def tmux_new(self: 'Server', session_name: str, command: str) -> None:
        """
        Start a tmux session on the server.

        Parameters
        ----------
        session_name : str
            The name of the session.
        command : str
            The command to execute.

        Returns
        -------

        See Also
        --------
        exec : Execute command on the server.
        tmux_kill : Stop a tmux session on the server.
        tmux_send_keys : Send keys to a tmux session on the server.
        """
        _ = self.exec(f'tmux -L {self.tmux_socket}' +
                      f' new-session -s {session_name} -d "{command}"')

    def tmux_kill(self: 'Server', session_name: str) -> None:
        """
        Stop all tmux sessions matching session_name.

        Parameters
        ----------
        session_name : str
            The name of the session.

        Returns
        -------

        See Also
        --------
        exec : Execute command on the server.
        tmux_new : Start a tmux session on the server.
        tmux_send_keys : Send keys to a tmux session on the server.
        """
        _ = self.exec(f'tmux -L {self.tmux_socket}' +
                      ' list-sessions | cut -d ":" -f 1 ' +
                      f'| grep {session_name} | xargs -I {{}} ' +
                      f'tmux -L {self.tmux_socket} kill-session -t {{}} || true')

    def tmux_send_keys(self: 'Server', session_name: str, keys: str) -> None:
        """
        Send keys to a tmux session on the server.

        Parameters
        ----------
        session_name : str
            The name of the session.
        keys : str
            The keys to execute.

        Returns
        -------

        See Also
        --------
        exec : Execute keys on the server.
        tmux_new : Start a tmux session on the server.
        tmux_kill : Stop a tmux session on the server.
        """
        _ = self.exec(f'tmux -L {self.tmux_socket}' +
                      f' send-keys -t {session_name} {keys}')

    def tmux_get_pid(self: 'Server', session_name: str) -> int:
        """
        Get the PID of the process running in a tmux session.

        Returns the PID of the child process of the tmux pane

        Parameters
        ----------
        session_name : str
            The name of the session.

        See Also
        --------
        tmux_new : Start a tmux session on the server.
        tmux_kill : Stop a tmux session on the server.
        """
        pane_pid = self.exec(f'tmux -L {self.tmux_socket}' +
                             f' list-panes -t {session_name}' +
                             " -F '#{pane_pid}'").strip()
        # pane_pid is the shell; get its child (the actual command)
        # child_pid = self.exec(f'pgrep -P {pane_pid}').strip()
        # return int(child_pid)
        return int(pane_pid)

    def tmux_is_alive(self: 'Server', session_name: str) -> bool:
        return self.test(f'tmux -L {self.tmux_socket}' +
                      f' list-sessions | grep {session_name}')

    def __copy_local(self: 'Server', source: str, destination: str, recursive: bool = False) -> None:
        """
        Copy a file from the localhost to the server.

        This method is called by the copy method if the server is localhost.

        Parameters
        ----------
        source : str
            The source file.
        destination : str
            The destination file.

        Returns
        -------

        See Also
        --------
        copy : Copy a file from the server to the localhost.
        __copy_ssh : Copy a file from the server to the server over SSH.
        """
        options = ""
        if recursive:
            options += " -r"

        self.__exec_local(f'cp{options} {source} {destination}')

    def __scp_to(self: 'Server', source: str, destination: str, recursive: bool = False) -> None:
        """
        Copy a file from the localhost to the server.

        This method is called by the copy method if the server is not
        localhost.

        Parameters
        ----------
        source : str
            The source file.
        destination : str
            The destination file.

        Returns
        -------

        See Also
        --------
        copy : Copy a file from the server to the localhost.
        __copy_local : Copy a file from the server to the server over SSH.
        __scp_from : Copy a file from the server to the server over SSH.
        """
        options = ""
        if self.ssh_config is not None:
            options = f" -F {self.ssh_config}"

        if recursive:
            options += " -r"

        sudo = ""
        if self.ssh_as_root == True:
            sudo = "sudo "

        self.__exec_local(f'{sudo}scp{options} {source} {self.fqdn}:{destination}')

    def __scp_from(self: 'Server', source: str, destination: str) -> None:
        """
        Copy a file from the server to the localhost.

        This method is called by the copy method if the server is not
        localhost.

        Parameters
        ----------
        source : str
            The source file.
        destination : str
            The destination file.

        Returns
        -------

        See Also
        --------
        copy : Copy a file from the server to the localhost.
        __copy_local : Copy a file from the server to the server over SSH.
        __scp_to : Copy a file from the server to the server over SSH.
        """
        options = ""
        if self.ssh_config is not None:
            options = f" -F {self.ssh_config}"

        sudo = ""
        if self.ssh_as_root == True:
            sudo = "sudo "

        self.__exec_local(f'{sudo}scp{options} "{self.fqdn}:{source}" "{destination}"')

    def copy_to(self: 'Server', source: str, destination: str, recursive: bool = False) -> None:
        """
        Copy a file from the localhost to the server.

        Parameters
        ----------
        source : str
            The source file.
        destination : str
            The destination file.

        Returns
        -------

        See Also
        --------
        __copy_local : Copy a file from the server to the server over SSH.
        __scp_to : Copy a file from the server to the server over SSH.
        copy_from : Copy a file from the server to the localhost.

        Example
        -------
        >>> server.copy_to('/home/user/file.txt', '/home/user/file.txt')
        """
        debug(f'Copying {source} to {self.log_name()}:{destination}')
        if self.localhost:
            self.__copy_local(source, destination, recursive=recursive)
        else:
            self.__scp_to(source, destination, recursive=recursive)

    def copy_from(self: 'Server', source: str, destination: str) -> None:
        """
        Copy a file from the server to the localhost.

        Parameters
        ----------
        source : str
            The source file.
        destination : str
            The destination file.

        Returns
        -------

        See Also
        --------
        __copy_local : Copy a file from the server to the server over SSH.
        __scp_from : Copy a file from the server to the server over SSH.
        copy_to : Copy a file from the localhost to the server.

        Example
        -------
        >>> server.copy_from('/home/user/file.txt', '/home/user/file.txt')
        """
        debug(f'Copying from {self.log_name()}:{source} to {destination}')
        self.__exec_local(f'mkdir -p {path_dirname(destination)} || true')
        if self.localhost:
            self.__copy_local(source, destination)
        else:
            self.__scp_from(source, destination)

    def wait_for_success(self: 'Server', command: str, timeout: int = 10
                         ) -> str:
        """
        Wait for a command to succeed.

        Parameters
        ----------
        command : str
            The command to execute.
        timeout : int
            The timeout in seconds.

        Returns
        -------

        See Also
        --------
        exec : Execute command on the server.
        """
        start = datetime.now()
        while (datetime.now() - start).total_seconds() < timeout:
            try:
                return self.exec(command)
            except Exception:
                sleep(1)

        raise TimeoutError(f'Execution on {self.log_name()} of command ' +
                           f'{command} timed out after {timeout} seconds')

    def test(self: 'Server', command: str) -> bool:
        try:
            _ = self.exec(command)
            return True
        except CalledProcessError:
            return False

    def wait_for_connection(self: 'Server', timeout: int = 10
                            ) -> None:
        """
        Wait for the server to be connected.

        Parameters
        ----------
        timeout : int
            The timeout in seconds.

        Returns
        -------
        """
        try:
            self.wait_for_success('echo', timeout)
        except TimeoutError:
            raise TimeoutError(f'Connection attempts to {self.log_name()} ' +
                               f'timed out after {timeout} seconds')

    def get_driver_for_device(self: 'Server', device_addr: str) -> str:
        """
        Get the driver for a device.

        Parameters
        ----------
        device : str
            The device's PCI bus address.

        Returns
        -------
        str
            The driver for the device.

        See Also
        --------
        """
        return self.exec(f'lspci -v -s {device_addr} | grep driver ' +
                         '| cut -d":" -f 2 | tr -d " "').replace('\n', '')

    def get_driver_for_nic(self: 'Server', iface: str) -> str:
        """
        Get the driver for a network interface.

        Note that this does not work, once the NIC is bound to DPDK.

        Parameters
        ----------
        iface : str
            The network interface name.

        Returns
        -------
        str
            The driver for the network interface.

        See Also
        --------

        Examples
        --------
        >>> server.get_driver_for_nic('enp176s0')
        'ixgbe'
        """
        return self.get_driver_for_device(self.get_nic_pci_address(iface))

    def is_test_iface_bound(self: 'Server') -> bool:
        """
        Check if the test interface is bound to DPDK.

        Parameters
        ----------

        Returns
        -------
        bool
            True if the test interface is bound to DPDK.
        """
        return (self.get_driver_for_device(self.test_iface_addr)
                == self.test_iface_dpdk_driv)

    def bind_device(self: 'Server', dev_addr: str, driver: str) -> None:
        """
        Bind a device to a driver.

        Parameters
        ----------
        dev_addr : str
            The device's PCI bus address.
        driver : str
            The driver to bind the device to.

        Returns
        -------
        """
        cmd = f'sudo dpdk-devbind.py -b {driver} {dev_addr}'

        if self.nixos:
            _ = self.exec(f'{self.__cmd_with_package("dpdk")} sh -c "{cmd}"')
        else:
            _ = self.exec(cmd)

    def unbind_device(self: 'Server', dev_addr: str) -> None:
        """
        Unbind a device from a driver.

        Parameters
        ----------
        dev_addr : str
            The device's PCI bus address.

        Returns
        -------
        """
        cmd = f'sudo dpdk-devbind.py -u {dev_addr}'

        if self.nixos:
            _ = self.exec(f'{self.__cmd_with_package("dpdk")} sh -c "{cmd}"')
        else:
            _ = self.exec(cmd)

    def bind_nics_to_dpdk(self: 'Server') -> None:
        """
        Bind all available network interfaces to DPDK.

        Parameters
        ----------

        Returns
        -------
        """
        cmd = f'cd {self.moongen_dir}/bin/libmoon; sudo ./bind-interfaces.sh'

        if self.nixos:
            _ = self.exec(f'{self.__cmd_with_package("dpdk")} sh -c "{cmd}"')
        else:
            _ = self.exec(cmd)

    def bind_test_iface(self: 'Server') -> None:
        """
        Bind test interface to DPDK.

        Parameters
        ----------

        Returns
        -------
        """
        # detect test interface if not known
        if not (self.test_iface_addr and self.test_iface_driv):
            self.detect_test_iface()

        # check if test interface is already bound
        if self.is_test_iface_bound():
            debug(f"{self.fqdn}'s test interface already bound to DPDK.")
            if not self._test_iface_id:
                self.detect_test_iface_id()
            return

        # bind test interface to DPDK
        self.exec(f'sudo modprobe {self.test_iface_dpdk_driv}')
        self.bind_device(self.test_iface_addr, self.test_iface_dpdk_driv)

        # get the test interface id
        self.detect_test_iface_id()

    def release_test_iface(self: 'Server') -> None:
        """
        Release test interface from DPDK.

        Parameters
        ----------

        Returns
        -------
        """
        self.bind_device(self.test_iface_addr, self.test_iface_driv)

    def detect_test_iface_id(self: 'Server') -> None:
        """
        Detect the test interface's DPDK ID.

        Parameters
        ----------

        Returns
        -------
        """
        cmd = ("dpdk-devbind.py -s | " +
               f"grep 'drv={self.test_iface_dpdk_driv}' || true")
        output: str
        if self.nixos:
            # nix shell prints debug output to stderr. We discard stderr.
            output = self.exec(f'{self.__cmd_with_package("dpdk")} sh -c "{cmd}" 2>/dev/null')
        else:
            output = self.exec(cmd)

        debug(f"Detecting test interface DPDK id on {self.fqdn}")

        for num, line in enumerate(output.splitlines()):
            if line.startswith(self.test_iface_addr):
                self._test_iface_id = num
                debug(f"Detected {self.fqdn}'s test interface DPDK id: {num}")
                return

        error(f"Failed to detect {self.fqdn}'s test interface DPDK id.")

    def has_pci_bus(self: 'Server') -> bool:
        """
        Check if the server has a PCI bus.

        Parameters
        ----------

        Returns
        -------
        bool
            True if the server has a PCI bus.
        """
        return self.exec('lspci')

    def detect_test_iface_by_mac(self: 'Server') -> None:
        """
        Detect the test interface by its MAC address.

        Parameters
        ----------

        Returns
        -------
        """
        output = self.exec("for d in /sys/class/net/*; " +
                           "do echo $(basename $d) $(cat $d/address); done")
        debug(f"Detecting test interface on {self.fqdn}")

        for line in output.splitlines():
            iface, mac = line.split()
            if mac != self.test_iface_mac:
                continue
            self.test_iface = iface
            debug(f"Detected {self.fqdn}'s test interface: {self.test_iface}")

            if not self.has_pci_bus():
                return

            self.test_iface_addr = self.get_nic_pci_address(self.test_iface)
            self.test_iface_driv = self.get_driver_for_nic(self.test_iface)
            return

        error(f"Failed to detect {self.fqdn}'s test interface.")

    def detect_test_iface(self: 'Server') -> None:
        """
        Detect the test interface if necessary.

        Parameters
        ----------

        Returns
        -------
        """
        if not (self.test_iface and self.test_iface_addr
                and self.test_iface_driv):
            self.detect_test_iface_by_mac()

    def setup_hugetlbfs(self: 'Server'):
        """
        Setup hugepage interface.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec(
            f"cd {self.moongen_dir}/bin/libmoon; " +
            "sudo bash ./setup-hugetlbfs.sh"
        )

    def get_nic_pci_address(self: 'Server', iface: str) -> str:
        """
        Get the PCI address for a network interface.

        Note that this does not work once the NIC is bound to DPDK.

        Parameters
        ----------
        iface : str
            The network interface identifier.

        Returns
        -------
        str
            The PCI bus address.

        Example
        -------
        >>> server.get_nic_pci_address('enp176s0')
        '0000:b0:00.0'
        """
        return self.exec(
            f"basename $(realpath /sys/class/net/{iface}/device " +
            "| sed \"s/\\/virtio[0-9]//g\")"
        ).replace('\n', '')

    def get_nic_mac_address(self: 'Server', iface: str) -> str:
        """
        Get the MAC address for a network interface.

        Parameters
        ----------
        iface : str
            The network interface identifier.

        Returns
        -------
        str
            The MAC address.

        Example
        -------
        >>> server.get_nic_pci_address('enp176s0')
        '64:9d:99:b1:0b:59'
        """
        return self.exec(f'cat /sys/class/net/{iface}/address')

    def get_nic_ip_addresses(self: 'Server', iface: str) -> list[str]:
        """
        Get the IP addresses for a network interface.

        Parameters
        ----------
        iface : str
            The network interface identifier.

        Returns
        -------
        List[str]
            The IP addresses.

        Example
        -------
        >>> server.get_nic_ip_addresses('enp176s0')
        ['192.168.0.1/24']
        """

        result = self.exec(f'ip addr show dev {iface}' +
                         ' | grep inet | awk "{print \\$2}"')

        if "does not exist" in result:
            debug("Interface {iface} does not exist!")
            return []

        else:
            return result.splitlines()


    def delete_nic_ip_addresses(self: 'Server', iface: str) -> None:
        """
        Delete the IP addresses for a network interface.

        Parameters
        ----------
        iface : str
            The network interface identifier.

        Returns
        -------

        Example
        -------
        >>> server.delete_nic_ip_addresses('enp176s0')
        """
        for addr in self.get_nic_ip_addresses(iface):
            self.exec(f'sudo ip addr del {addr} dev {iface}')

    def add_arp_entries(self: 'Server', others: Dict[int, Type['Server']]):
        for vm_num, other_vm in others.items():
            ip = strip_subnet_mask(other_vm.test_iface_ip_net)
            mac = MultiHost.mac(other_vm.test_iface_mac, vm_num)
            dev = self.test_iface
            self.exec(f"sudo ip neighbour add {ip} dev {dev} lladdr {mac}")

    def start_moongen_reflector(self: 'Server'):
        """
        Start the libmoon L2 reflector.

        Parameters
        ----------

        Returns
        -------
        """
        self.tmux_new('reflector', f'cd {self.moongen_dir}; sudo bin/MoonGen '
                      + path_join(self.project_root, 'reflector.lua') +
                      f' {self._test_iface_id}')

    def stop_moongen_reflector(self: 'Server'):
        """
        Stop the libmoon L2 reflector.

        Parameters
        ----------

        Returns
        -------
        """
        self.tmux_kill('reflector')

    def start_xdp_pure_reflector(self: 'Server', iface: str = None):
        if not iface:
            iface = self.test_iface
        project_root = str(Path(self.project_root) / "../..") # nix wants nicely formatted paths
        xdgDir = f"{project_root}/xdp-pure"
        xdgProgram = f"{xdgDir}/lib/pure_reflector.o"

        # compile xdp program for the Servers MAC address
        LOCAL_MAC = f"{{ 0xb4, 0x96, 0x91, 0xb3, 0x8b, 0x04 }}" # TODO
        flakeUrl = f"git+file:///{project_root}?rev=$(cd {project_root}; git rev-parse HEAD)"
        nixExpr = f'(builtins.getFlake {flakeUrl}).packages.x86_64-linux.xdp-reflector.overrideAttrs (_: _: {{ LOCAL_MAC = \\"{LOCAL_MAC}\\"; }})'
        self.exec(f'nix build --expr "{nixExpr}" -o {xdgDir}')

        self.exec(f'sudo ip link set {iface} promisc on')
        self.exec(f'sudo ip link set {iface} xdpgeneric obj ' +
                  f'{xdgProgram} sec xdp')
        self.exec(f'sudo ip link set {iface} up')

    def stop_xdp_pure_reflector(self: 'Server', iface: str = None):
        if not iface:
            iface = self.test_iface
        self.exec(f'sudo ip link set {iface} xdpgeneric off || true')
        self.exec(f'sudo ip link set {iface} promisc off || true')

    def start_xdp_reflector(self: 'Server', iface: str = None):
        """
        Start the xdp reflector.

        Parameters
        ----------
        iface : str
            The network interface identifier.

        Returns
        -------

        Examples
        --------
        >>> server.start_xdp_reflector('enp176s0')
        """
        refl_obj_file_path = path_join(self.xdp_reflector_dir, 'reflector.o')
        if not iface:
            iface = self.test_iface
        self.exec(f'sudo ip link set {iface} xdpgeneric obj ' +
                  f'{refl_obj_file_path} sec xdp')
        self.exec(f'sudo ip link set {iface} up')

    def stop_xdp_reflector(self: 'Server', iface: str = None):
        """
        Stop the xdp reflector.

        Parameters
        ----------
        iface : str
            The network interface identifier.

        Returns
        -------

        Examples
        --------
        >>> server.stop_xdp_reflector('enp176s0')
        """
        if not iface:
            iface = self.test_iface
        self.exec(f'sudo ip link set {iface} xdpgeneric off || true')


    def start_ycsb(self, fqdn: str, rate: int = 100, runtime: int = 8, threads: int = 8, port: int = 6379, outfile: str = "/tmp/outfile.log", load: bool = False):
        """
        rate: target requests rate per second. -1 to request at max rate
        runtime: in secs
        load: load test data instead of running a test. Ignores many arguments.
        """
        # some general usage docs: https://github.com/brianfrankcooper/YCSB/wiki/Running-a-Workload
        # docs for generic -p parameters: https://github.com/brianfrankcooper/YCSB/wiki/Core-Properties
        # docs for redis -p parameters: https://github.com/brianfrankcooper/YCSB/blob/master/redis/README.md
        ycsb_path = f"{self.project_root}/../../ycsb"
        workloads_path = f"{ycsb_path}/share/workloads"
        if not load:
            ops = 429496729 # MAX_INT
            core_properties = f"-p operationcount={ops}" \
                    f" -p maxexecutiontime={runtime}"
            if rate is None or rate == -1:
                target_rate = ""
            else:
                target_rate = f"-target {rate}"

            ycsb_cmd = f'{ycsb_path}/bin/ycsb-wrapped run redis -s -P {workloads_path}/workloada -p redis.host={fqdn} -p redis.port={port} {core_properties} -threads {threads} {target_rate}'
        else:
            ycsb_cmd = f'{ycsb_path}/bin/ycsb-wrapped load redis -s -P {workloads_path}/workloada -p redis.host={fqdn} -p redis.port={port} -threads {threads}'
        self.tmux_new('ycsb', f'{ycsb_cmd} 2>&1 | tee {outfile}; echo AUTOTEST_DONE >> {outfile}; sleep 999');
        # error indicating strings: in live-status updates: READ-FAILED WRITE-FAILED end-report:
        # [READ], Return=ERROR


    def stop_ycsb(self):
        self.tmux_kill("ycsb")


    def start_click(self, program: str, outfile: str, script_args: dict = dict(), dpdk: bool = True):
        """
        program: path to .click file relative to project root
        outfile: path to remote log file
        script_args: arguements to override click scripts define() directive variables
        """
        click_bin = f"{self.project_root}/nix/builds/click/bin/click"
        args = ' '.join([f'{key}={value}' for key, value in script_args.items()])
        dpdk_args = ""
        if dpdk:
            dpdk_args = f'--dpdk \'-l 0\' --'
        self.tmux_new('click', f'{click_bin} {dpdk_args} {program} {args} 2>&1 | tee {outfile}; echo AUTOTEST_DONE >> {outfile}; sleep 999');


    def stop_click(self):
        self.exec("pkill click || true")


    def kill_click(self):
        self.tmux_kill("click")


    def upload_moonprogs(self: 'Server', source_dir: str):
        """
        Upload the MoonGen programs to the server.

        Parameters
        ----------
        source_dir : str
            The local directory containing the MoonGen programs.

        Returns
        -------
        """
        self.exec(f'mkdir -p {self.project_root}')
        for file in listdir(source_dir):
            self.copy_to(path_join(source_dir, file), self.project_root)

    def modprobe_test_iface_drivers(self, interface: Optional[Interface] = None):
        """
        Modprobe the test interface drivers.

        Parameters
        ----------
        interface: may be given e.g. for guests that have NICs diverging from what is set in the config

        Returns
        -------
        """
        if interface is None:
            self.exec(f'sudo modprobe {self.test_iface_driv}')
        else:
            self.exec(f'sudo modprobe {interface.guest_driver()}')


    def update_extra_hosts(self, extra_hosts: str):
        self.write(extra_hosts, "/tmp/extra_hosts")
        self.exec("rm /etc/hosts")
        self.exec("cat /etc/static/hosts > /etc/hosts")
        self.exec("cat /tmp/extra_hosts >> /etc/hosts")


    def start_ptp_client(self, out_dir: str):
        self.exec(f": > {out_dir}")
        project_root = str(Path(self.project_root) / "../..") # nix wants nicely formatted paths
        self.tmux_new("ptpclient", f"sudo {project_root}/test/ptptest/build/ptpclient -l 0 -n 4 -a {self.test_iface_addr} -- T 0 -p 1 >> {out_dir}; sleep 999")


    def stop_ptp_client(self):
        self.tmux_kill("ptpclient")


    # sudo vpp -c ./benchmark/configurations/vpp.conf
    # sudo vppctl -s /tmp/vpp-cli
    # show log
    # show interface
    # create vhost-user socket /tmp/vhost-user0
    # set int state VirtualEthernet0/0/0 up
    # set interface l2 xconnect GigabitEthernet0/8/0.300 GigabitEthernet0/9/0.300
    def start_vpp(self: 'Server', num_vms: int = 0):
        self.tmux_kill('vpp')

        remote_config_file = "/tmp/vpp.conf"
        remote_startup_file = "/tmp/vpp.exec"
        remote_vpp_sock = "/tmp/vpp-cli"
        vpp_bin = f"{self.project_root}/.nix-builds/vpp/bin/vpp"
        pnic_interface = "pNIC0"
        num_interfaces = len(MultiHost.range(num_vms)) + 1 # num_vms 0 refers to 1 interface actually. Plus one for the load generator
        vhost_user_interfaces = [ f"VirtualEthernet0/0/{i}" for i in range(num_interfaces) ]
        remote_sockets = []

        # TODO: cpu pinning!
        # escape { with {{
        config = f"""
        unix {{
            cli-listen {remote_vpp_sock}
            log /tmp/vpp.log
            nodaemon
        }}

        dpdk {{
            socket-mem 1024,1024
            uio-driver vfio-pci
        }}
        """
        # dpdk {{
        #     dev {self.test_iface_addr} {{
        #         name {pnic_interface}
        #     }}
        # }}

        startup_exec = ""
        # create vhost-user interfaces
        loadgen_socket = MultiHost.vhost_user_sock('loadgen')
        startup_exec += f"create vhost-user socket {loadgen_socket} server\n"
        remote_sockets += [ loadgen_socket ]
        for vm_number in MultiHost.range(num_vms):
            vm_socket = MultiHost.vhost_user_sock(vm_number)
            startup_exec += f"create vhost-user socket {vm_socket} server\n"
            remote_sockets += [ vm_socket ]
        # set vhost-user interfaces up
        for interface in vhost_user_interfaces:
            startup_exec += f"set int state {interface} up\n"
        # connect vhost-user interfaces in a ring topology (the load generator is not a forwarder, so it will break the loop)
        for i in range(num_interfaces):
            intA = vhost_user_interfaces[i]
            intB = vhost_user_interfaces[(i+1) % num_interfaces]
            startup_exec += f"set int l2 xconnect {intA} {intB}\n"

        self.exec(f"sudo rm {remote_config_file} || true")
        self.exec(f"sudo rm {remote_startup_file} || true")
        self.write(config, remote_config_file)
        self.write(startup_exec, remote_startup_file)

        self.exec("; ".join([ f"sudo rm {socket} || true" for socket in remote_sockets ]))
        # sockets have to pre-exist. Well apparently not cause this is commented.
        # self.exec(f'python -c "import socket as s; sock = s.socket(s.AF_UNIX); sock.bind(\'{remote_socket}\')"')

        # start vpp
        cmd = f"sudo {vpp_bin} -c {remote_config_file} | tee /tmp/foo.log; sleep 999"
        self.tmux_new('vpp', cmd)

        # run startup exec manually so that we block ontil vpp is online
        self.wait_for_success(self.vpp_exec_cmd("show int"))
        self.exec(self.vpp_exec_cmd(startup_exec))


    def stop_vpp(self: 'Server'):
        self.exec("sudo pkill vpp || true") # tmux doesn't kill it properly
        self.tmux_kill('vpp')

    def vpp_exec_cmd(self: 'Server', cmd: str):
        remote_vpp_sock = "/tmp/vpp-cli"

        # i think vppctl does unnecessary stuff to beak this automation
        # vppctl_bin = f"{self.project_root}/nix/builds/vpp/bin/vppctl"
        # self.exec(f"echo '{cmd}' | sudo {vppctl_bin} -s {remote_vpp_sock}")

        # simple solution, best solution: just works
        pipefail_prefix = "set -o pipefail; " # make command fail if socat fails (ignore that strings always succeeds)
        cmd = f"{pipefail_prefix}echo '{cmd}' | sudo socat - UNIX-CONNECT:{remote_vpp_sock} | strings"
        return cmd


class BatchExec:
    """
    Execution through ssh brings overheads of authentication etc.
    As a mitigation, this class helps to batch commands into a single ssh command to reduce ssh-based overheads.
    """
    server: Server
    batchsize: int
    batch = []

    def __init__(self, server: Server, batchsize: int):
        self.server = server
        self.batchsize = batchsize
        self.batch = []

    def exec(self, cmd: str):
        self.batch += [cmd]
        if len(self.batch) >= self.batchsize:
            self.flush()

    def flush(self):
        if len(self.batch) == 0:
            return
        fat_cmd = "; ".join(self.batch)
        self.server.exec(fat_cmd)
        self.batch = []


class Host(Server):
    """
    Host class.

    This class represents a host, so the server that runs guest VMs. In out
    case it is also used for physical NIC tests.

    See Also
    --------
    Server : Server class.
    Guest : Guest class.
    LoadGen : LoadGen class.

    Examples
    --------
    >>> Host('server.test.de')
    Host(fqdn='server.test.de')
    """
    admin_bridge: str
    admin_bridge_ip_net: str
    admin_tap: str
    test_iface_vfio_driv: str
    test_bridge: str
    test_tap: str
    test_macvtap: str
    vmux_path: str
    vmux_socket_path: str
    guest_admin_iface_mac: str
    guest_test_iface_mac: str
    guest_root_disk_path: str
    guest_vcpus: int
    guest_memory: int
    fsdevs: dict[str, str]
    has_hugepages1g: bool

    def __init__(self: 'Host',
                 fqdn: str,
                 admin_bridge: str,
                 admin_bridge_ip_net: str,
                 admin_tap: str,
                 test_iface: str,
                 test_iface_addr: str,
                 test_iface_mac: str,
                 test_iface_driv: str,
                 test_iface_dpdk_driv: str,
                 test_iface_vfio_driv: str,
                 test_bridge: str,
                 test_bridge_ip_net: Optional[str],
                 test_tap: str,
                 test_macvtap: str,
                 vmux_path: str,
                 vmux_socket_path: str,
                 guest_root_disk_path: str,
                 guest_admin_iface_mac: str,
                 guest_test_iface_mac: str,
                 guest_vcpus: int,
                 guest_memory: int,
                 fsdevs: dict[str, str],
                 tmux_socket: str,
                 moongen_dir: str,
                 project_root: str,
                 xdp_reflector_dir: str,
                 localhost: bool = False,
                 ssh_config: Optional[str] = None,
                 ssh_as_root: bool = False) -> None:
        """
        Initialize the Host class.

        Parameters
        ----------
        fqdn : str
            The fully qualified domain name of the host.
        admin_bridge : str
            The network interface identifier of the admin bridge interface.
        admin_bridge_ip_net : str
            The IP address and subnet mask of the admin bridge interface.
        admin_tap : str
            The network interface identifier of the admin tap interface.
        test_iface : str
            The name of the test interface.
        test_iface_addr : str
            The IP address of the test interface.
        test_iface_mac : str
            The MAC address of the test interface.
        test_iface_driv : str
            The driver of the test interface.
        test_iface_dpdk_driv : str
            The DPDK driver of the test interface.
        test_iface_vfio_driv : str
            The vfio driver of the test interface.
        test_bridge : str
            The network interface identifier of the test bridge interface.
        test_bridge_ip_net : Optional[str]
            IP net assigned to the test bridge.
        test_tap : str
            The network interface identifier of the test tap interface.
        test_macvtap : str
            The network interface identifier of the test macvtap interface.
        vmux_path : str
            Path to the vmux executable.
        vmux_socket_path : str
            The path to the vmux socket.
        guest_root_disk_path : str
            The path to the root disk of the guest.
        guest_admin_iface_mac : str
            The MAC address of the guest admin interface.
        guest_test_iface_mac : str
            The MAC address of the guest test interface.
        guest_vcpus : int
            The default number of vCPUs of the guest.
        guest_memory : int
            The default memory in MiB of the guest.
        fsdevs : dict[str, str]
            The name and path pairs for fs devices to be passed to the guest.
        tmux_socket : str
            The name for the tmux socket.
        moongen_dir : str
            The directory of the MoonGen installation.
        moonprogs_dir : str
            The directory with the MoonGen Lua programs.
        xdp_reflector_dir : str
            The directory of the xdp reflector installation.
        localhost : bool
            True if the host is localhost.
        ssh_config : Optional[str]
            Path to local ssh config to use to connect with.

        Returns
        -------
        Host : The Host object.

        See Also
        --------
        Server : The Server class.
        Server.__init__ : Initialize the Server class.

        Examples
        --------
        >>> Host('server.test.de')
        Host(fqdn='server.test.de')
        """
        super().__init__(fqdn, test_iface, test_iface_addr, test_iface_mac,
                         test_iface_driv, test_iface_dpdk_driv,
                         tmux_socket, moongen_dir, project_root,
                         xdp_reflector_dir, localhost, ssh_config=ssh_config,
                         ssh_as_root=ssh_as_root)
        self.admin_bridge = admin_bridge
        self.admin_bridge_ip_net = admin_bridge_ip_net
        self.admin_tap = admin_tap
        self.test_iface_vfio_driv = test_iface_vfio_driv
        self.test_bridge = test_bridge
        self.test_bridge_ip_net = test_bridge_ip_net
        self.test_tap = test_tap
        self.test_macvtap = test_macvtap
        self.vmux_path = vmux_path
        self.vmux_socket_path = vmux_socket_path
        self.guest_test_iface_mac = guest_test_iface_mac
        self.guest_admin_iface_mac = guest_admin_iface_mac
        self.guest_root_disk_path = guest_root_disk_path
        self.guest_vcpus = guest_vcpus
        self.guest_memory = guest_memory
        self.fsdevs = fsdevs
        self.has_hugepages1g = self.isdir("/dev/hugepages1G")

    def setup_admin_bridge(self: 'Host'):
        """
        Setup the admin bridge.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec('sudo modprobe bridge')
        self.exec(f'sudo ip link show {self.admin_bridge} 2>/dev/null' +
                  f' || (sudo ip link add {self.admin_bridge} type bridge; ' +
                  f'sudo ip addr add {self.admin_bridge_ip_net} ' +
                  f'dev {self.admin_bridge}; true)')
        self.exec(f'sudo ip link set {self.admin_bridge} up')

    def setup_admin_tap(self: 'Host', vm_range: range = range(0)):
        """
        Setup the admin tap.

        This sets up the tap device for the admin interface of the guest VM.
        So the interface to SSH connections and stuff.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec('sudo modprobe tun tap')

        buffer = BatchExec(self, 10)

        def setup(admin_tap):
            buffer.exec(f'sudo ip link show {admin_tap} 2>/dev/null' +
                      f' || (sudo ip tuntap add {admin_tap} mode tap;' +
                      f' sudo ip link set {admin_tap} '
                      f'master {self.admin_bridge}; true)')
            buffer.exec(f'sudo ip link set {admin_tap} up')

        if len(vm_range) == 0:
            setup(MultiHost.iface_name(self.admin_tap, 0))
            buffer.flush()
            return

        for i in vm_range:
            admin_tap = MultiHost.iface_name(self.admin_tap, i)
            setup(admin_tap)

        buffer.flush()

    def modprobe_test_iface_drivers(self):
        """
        Modprobe the test interface drivers.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec(f'sudo modprobe {self.test_iface_driv}')
        self.exec(f'sudo modprobe {self.test_iface_dpdk_driv}')
        self.exec(f'sudo modprobe {self.test_iface_vfio_driv}')

    def setup_test_br_tap(self: 'Host', multi_queue=True, vm_range: range = range(0)):
        """
        Setup the bridged test tap device.

        This sets up the tap device for the test interface of the guest VM.
        So the VirtIO device.

        Parameters
        ----------

        Returns
        -------
        """
        if BRIDGE_QUEUES == 0:
            multi_queue = False


        # load kernel modules
        self.exec('sudo modprobe bridge tun tap')
        username = self.whoami()

        # create bridge and add the physical NIC to it
        self.exec(f'sudo ip link show {self.test_bridge} 2>/dev/null ' +
                  f' || (sudo ip link add {self.test_bridge} type bridge; ' +
                  'true)')
        if self.test_bridge_ip_net is not None:
            self.exec(f'sudo ip addr add {self.test_bridge_ip_net} ' +
                      f'dev {self.test_bridge}; true')
        test_iface_output = self.exec(f'sudo ip link show {self.test_iface}')
        if f'master {self.test_bridge}' not in test_iface_output:
            self.exec(f'sudo ip link set {self.test_iface} ' +
                      f'master {self.test_bridge}')

        buffer = BatchExec(self, 10)

        def setup(test_tap):
            # create tap and add to bridge
            buffer.exec(f'sudo ip link show {test_tap} 2>/dev/null || ' +
                      f'(sudo ip tuntap add dev {test_tap} mode tap ' +
                      f'user {username}{" multi_queue" if multi_queue else ""}; true)')
            buffer.exec(f'if [[ "$(sudo ip link show {test_tap})" != *"master {self.test_bridge}"* ]]; then sudo ip link set {test_tap} master {self.test_bridge}; fi')
            # tap_output = self.exec(f'sudo ip link show {test_tap}')
            # if f'master {self.test_bridge}' not in tap_output:
            #     self.exec(f'sudo ip link set {test_tap} ' +
            #               f'master {self.test_bridge}')

            # bring up all interfaces (nic, bridge and tap)
            buffer.exec(f'sudo ip link set {self.test_iface} up ' +
                      f'&& sudo ip link set {self.test_bridge} up ' +
                      f'&& sudo ip link set {test_tap} up')

        if len(vm_range) == 0:
            setup(MultiHost.iface_name(self.test_tap, 0))
            buffer.flush()
            return

        for i in vm_range:
            test_tap = MultiHost.iface_name(self.test_tap, i)
            setup(test_tap)

        buffer.flush()

        # if self.test_bridge_ip_net:
        #     self.exec(f'sudo ip address add {self.test_bridge_ip_net} dev {self.test_bridge}')

    def destroy_test_br_tap(self: 'Host'):
        """
        Destroy the bridged test tap device.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec(f'sudo ip link delete {self.test_bridge} || true')
        self.exec(f'ls /sys/class/net | grep {MultiHost.iface_name(self.test_tap, -1)} | xargs -I {{}} sudo ip link delete {{}} | true')

    def setup_test_macvtap(self: 'Host'):
        """
        Setup the macvtap test interface.

        This sets up the macvtap device for the test interface of the guest VM.
        So the VirtIO device.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec('sudo modprobe macvlan')
        self.exec(f'sudo ip link show {self.test_macvtap} 2>/dev/null' +
                  f' || sudo ip link add link {self.test_iface}' +
                  f' name {self.test_macvtap} type macvtap')
        self.exec(f'sudo ip link set {self.test_macvtap} address ' +
                  f'{self.guest_test_iface_mac} up')
        self.exec('sudo chmod 666' +
                  f' /dev/tap$(cat /sys/class/net/{self.test_macvtap}/ifindex)'
                  )

    def destroy_test_macvtap(self: 'Host'):
        """
        Destroy the macvtap test interface.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec(f'sudo ip link delete {self.test_macvtap} || true')

    def run_guest(self: 'Host',
                  net_type: Interface,
                  machine_type: str,
                  vcpus: int = None,
                  memory: int = None,
                  root_disk: str = None,
                  debug_qemu: bool = False,
                  ioregionfd: bool = False,
                  qemu_build_dir: str = None,
                  vhost: bool = False,
                  rx_queue_size: int = 256,
                  tx_queue_size: int = 256,
                  vm_number: int = 0,
                  extkern: Optional[str] = None,
                  ) -> None:
        # TODO this function should get a Guest object as argument
        """
        Run a guest VM.

        Parameters
        ----------
        net_type : str
            Test interface network type
        machine_type : str
            Guest machine type
        vcpus : int
            Number of vCPUs, overwrites the default value in Host.guest_vcpus.
        memory : int
            Amount of memory in MiB, overwrites the default value in
            Host.guest_memory.
        root_disk : str
            Path to the disk file for guest's root partition
        debug_qemu : bool
            True if you want to attach GDB to Qemu. The GDB server will
            be bound to port 1234.
        ioregionfd : bool
            True if you want to use the IORegionFD enhanced virtio_net_device
            for the test interface.
        qemu_build_dir : str
            Path to the Qemu build directory. Can be empty if you want to use
            the installed Qemu.
        vhost : bool
            True if you want to use vhost on the test interface.
        rx_queue_size : int
            Size of the receive queue for the test interface.
        tx_queue_size : int
            Size of the transmit queue for the test interface.
        vm_number: int
            If not set to 0, will start VM in a way that other VMs with different vm_number can be started at the same time.
        extkern: Optional[str]
            If not None, another root_disk will be booted with an external kernel which allows us to append str to the kernel command line.


        Returns
        -------
        """
        # TODO this command should be build by the Guest object
        # it should take all the settings from the config file
        # and compile them.

        # Build misc parameters

        dev_type = 'pci' if machine_type == 'pc' else 'device'

        # TODO we need a different qemu build dir for vmux
        qemu_bin_path = 'qemu-system-x86_64'
        if qemu_build_dir:
            qemu_bin_path = path_join(qemu_build_dir, qemu_bin_path)

        cpus = vcpus if vcpus else self.guest_vcpus
        mem = memory if memory else self.guest_memory
        disk_path = self.guest_root_disk_path
        if root_disk:
            disk_path = root_disk

        disk_path = MultiHost.disk_path(disk_path, vm_number)
        fsdev_config = ''
        if self.fsdevs:
            for name, path in self.fsdevs.items():
                fsdev_config += (
                    f' -fsdev local,path={path},security_model=none,' +
                    f'id={name}fs' +
                    f' -device virtio-9p-{dev_type},mount_tag={name},' +
                    f'fsdev={name}fs'
                )

        # Build test network parameters
        test_net_config = self._test_network_qemu_args(net_type, ioregionfd, vhost, dev_type, vm_number, rx_queue_size, tx_queue_size)

        # Actually start qemu in tmux
        project_root = str(Path(self.project_root) / "../..") # nix wants nicely formatted paths
        extkern_options = ""
        if extkern is not None:
            extkern_options = ("" +
                f' -kernel {project_root}/nix/results/test-guest-kernel/bzImage' +
                f' -initrd {project_root}/nix/results/test-guest-initrd/initrd' +
                f' -append \\"root=/dev/vda console=ttyS0 init=/init $(cat {project_root}/nix/results/test-guest-kernelParams) {extkern}\\"')

        project_root = str(Path(self.project_root)) # nix wants nicely formatted paths
        nix_shell = f"nix shell --inputs-from {project_root} nixpkgs#numactl --command"
        numactl = f"numactl -C {self.cpupinner.qemu(vm_number)}"
        # numactl = ""

        self.tmux_new(
            MultiHost.enumerate('qemu', vm_number),
            ('gdbserver 0.0.0.0:1234 ' if debug_qemu else '') +
            f"sudo {nix_shell} {numactl} " +
            qemu_bin_path +
            f' -machine {machine_type}' +
            ' -cpu host' +
            f' -smp {cpus}' +

            # shared memory
            f' -m {mem}' +
            self._memory_backend(mem, vm_number) +

            # optionally a linux kernel
            extkern_options +

            ' -display none' + # avoid opening all the vnc ports
            ' -enable-kvm' +
            f' -drive id=root,format=qcow2,file={disk_path},'
            'if=none,cache=none' +
            f' -device virtio-blk-{dev_type},id=rootdisk,drive=root' +
            (',use-ioregionfd=true' if ioregionfd else '') +
            f',queue-size={rx_queue_size}' +
            # ' -cdrom /home/networkadmin/images/guest_init.iso' +
            fsdev_config +
            ' -serial stdio' +
            (' -monitor tcp:127.0.0.1:2345,server,nowait' if debug_qemu else '') +
            f' -netdev tap,vhost=on,id=admin0,ifname={MultiHost.iface_name(self.admin_tap, vm_number)},' +
            'script=no,downscript=no' +
            f' -device virtio-net-{dev_type},id=admif,netdev=admin0,' +
            f'mac={MultiHost.mac(self.guest_admin_iface_mac, vm_number)}' +
            test_net_config
            # +
            # ' -drive id=test1,format=raw,file=/dev/ssd/test1,if=none,' +
            # 'cache=none' +
            # f' -device virtio-blk-{dev_type},id=test1,drive=test1' +
            # ' -drive id=test2,format=raw,file=/dev/ssd/test2,if=none,' +
            # 'cache=none' +
            # f' -device virtio-blk-{dev_type},id=test2,drive=test2'
            # +
            # ' --trace virtio_mmio_read --trace virtio_mmio_write' +
            +
            f' 2>/tmp/trace-vm{vm_number}.log'
            )

    def kill_guest(self: 'Host') -> None:
        """
        Kill all guest VMs.

        Parameters
        ----------

        Returns
        -------
        """
        self.tmux_kill('qemu')

    def run_confidential_guest(self: 'Host',
                  net_type: Interface,
                  vcpus: int = None,
                  memory: int = None,
                  root_disk: str = None,
                  debug_qemu: bool = False,
                  ioregionfd: bool = False,
                  qemu_build_dir: str = None,
                  vhost: bool = False,
                  rx_queue_size: int = 256,
                  tx_queue_size: int = 256,
                  vm_number: int = 0,
                  extkern: Optional[str] = None,
                  confidential: bool = True,
                  iommu_hack: bool = False,
                  ) -> None:
        # TODO this function should get a Guest object as argument
        # TODO this command should be build by the Guest object
        # it should take all the settings from the config file
        # and compile them.

        # Build misc parameters

        dev_type = 'pci'

        # TODO we need a different qemu build dir for vmux
        qemu_bin_path = 'qemu-system-x86_64'
        if qemu_build_dir:
            qemu_bin_path = path_join(qemu_build_dir, qemu_bin_path)

        cpus = vcpus if vcpus else self.guest_vcpus
        mem = memory if memory else self.guest_memory
        disk_path = self.guest_root_disk_path
        if root_disk:
            disk_path = root_disk

        disk_path = MultiHost.disk_path(disk_path, vm_number)
        fsdev_config = ''
        if self.fsdevs:
            for name, path in self.fsdevs.items():
                fsdev_config += (
                    f' -fsdev local,path={path},security_model=none,' +
                    f'id={name}fs' +
                    f' -device virtio-9p-{dev_type},mount_tag={name},' +
                    f'fsdev={name}fs'
                )

        # Build test network parameters
        test_net_config = self._test_network_qemu_args(net_type, ioregionfd, vhost, dev_type, vm_number, rx_queue_size, tx_queue_size, iommu_hack=iommu_hack)

        # Actually start qemu in tmux
        project_root = str(Path(self.project_root) / "../..") # nix wants nicely formatted paths
        extkern_options = ""
        if extkern is not None:
            extkern_options = ("" +
                f' -kernel {project_root}/nix/results/test-guest-kernel/bzImage' +
                f' -initrd {project_root}/nix/results/test-guest-initrd/initrd' +
                f' -append \\"root=/dev/vda console=ttyS0 init=/init $(cat {project_root}/nix/results/test-guest-kernelParams) {extkern}\\"')

        project_root = str(Path(self.project_root)) # nix wants nicely formatted paths
        nix_shell = f"nix shell --inputs-from {project_root} nixpkgs#numactl --command"
        numactl = "" # f"numactl -C {self.cpupinner.qemu(vm_number)}" # we pin vcpus instead
        # numactl = ""

        self.tmux_new(
            MultiHost.enumerate('qemu', vm_number),
            ('gdbserver 0.0.0.0:1234 ' if debug_qemu else '') +
            f"sudo {nix_shell} {numactl} " +
            # "gdb -q -ex 'set pagination off' -ex 'handle all nostop' -ex run --args " +
            qemu_bin_path +
            (f' -machine q35,confidential-guest-support=sev0,memory-backend=ram1' if confidential else f' -machine q35,memory-backend=ram1') +
            (f' -object sev-snp-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,init-flags=4,igvm-file={self.project_root}/svsm/bin/coconut-qemu.igvm' if confidential else '') +
            ' -cpu EPYC-v4,host-phys-bits=true' +
            f' -smp {cpus}' +

            # shared memory
            # f' -m {mem}' +
            f' -object memory-backend-memfd,id=ram1,size={mem}M,share=true' +

            # optionally a linux kernel
            extkern_options +

            ' -display none' + # avoid opening all the vnc ports
            ' -enable-kvm' +
            ' -no-reboot' +
            f' -drive id=root,format=qcow2,file={disk_path},'
            'if=none,cache=none' +
            f' -device virtio-blk-{dev_type},id=rootdisk,drive=root' +
            (',use-ioregionfd=true' if ioregionfd else '') +
            f',queue-size={rx_queue_size}' +
            # ' -cdrom /home/networkadmin/images/guest_init.iso' +
            fsdev_config +
            # ' -serial stdio' +
            ' -chardev stdio,id=char0,logfile=/tmp/serial.log,signal=off' +
            ' -serial chardev:char0' +
	        f' -qmp unix:{MultiHost.qmp_path(vm_number)},server=on,wait=off' +
            (' -monitor tcp:127.0.0.1:2345,server,nowait' if debug_qemu else '') +
            f' -netdev tap,vhost=on,id=admin0,ifname={MultiHost.iface_name(self.admin_tap, vm_number)},' +
            'script=no,downscript=no' +
            f' -device e1000,id=admif,netdev=admin0,' +
            f'mac={MultiHost.mac(self.guest_admin_iface_mac, vm_number)}' +
            test_net_config
            # +
            # ' -drive id=test1,format=raw,file=/dev/ssd/test1,if=none,' +
            # 'cache=none' +
            # f' -device virtio-blk-{dev_type},id=test1,drive=test1' +
            # ' -drive id=test2,format=raw,file=/dev/ssd/test2,if=none,' +
            # 'cache=none' +
            # f' -device virtio-blk-{dev_type},id=test2,drive=test2'
            # +
            # ' --trace virtio_mmio_read --trace virtio_mmio_write' +
            +
            f' 2>/tmp/trace-vm{vm_number}.log; echo qemu done; sleep 999'
            )

        self.pin_vcpus(vm_number, int(cpus))

    def pin_vcpus(self: 'Host', vm_number: int, cpus: int):
        json_line = self.wait_for_success("echo '{\"execute\": \"qmp_capabilities\"}\n{\"execute\": \"query-cpus-fast\"}' | sudo socat - unix-connect:" + MultiHost.qmp_path(vm_number) + " | grep return") # fail unless qmp actually responds with the return json and not only the capabilities
        qmp_response = json.loads(json_line.splitlines()[-1])
        vcpus = qmp_response["return"]
        assert len(vcpus) == cpus, f"We told Qemu to start with {cpus} but now Qemu only knowns {len(vcpus)} vcpus."
        cmds = []
        for vcpu, target_core in zip(vcpus, self.cpupinner.qemu_vcpus(vm_number, cpus) ):
            tid = vcpu["thread-id"]
            cmds += [f"sudo taskset -cp {target_core} {tid}"]
        self.exec("; ".join(cmds))

    def kill_confidential_guest(self: 'Host') -> None:
        """
        Kill all guest VMs.

        Parameters
        ----------

        Returns
        -------
        """
        self.tmux_kill('qemu')

    def _memory_backend(self: 'Host', mem: int, vm_number: int) -> str:
        """
        Build memory backend parameters. Needed for some setups like vhost-user or vfio-user.
        We also keep it in other cases so that every VM uses hugepages consistently.
        """

        if self.has_hugepages1g:
            memory_path = f'/dev/hugepages/qemu-memory{vm_number}'
        else:
            memory_path = f'/dev/shm/qemu-{vm_number}'
        # if path_dirname(memory_path) != mem * 1024 * 1024:
        if self.test(f"[[ -f {memory_path} && $(stat --printf='%s' {memory_path}) -eq {int(mem)*1024*1024} ]]"):
            self.exec(f"sudo rm {memory_path}")

        memory_backend = f' -object memory-backend-file,mem-path={memory_path},prealloc=yes,id=bm,size={mem}M,share=on' + \
                          ' -numa node,memdev=bm'

        return memory_backend

    def _test_network_qemu_args(self: 'Host', net_type, ioregionfd, vhost, dev_type, vm_number, rx_queue_size, tx_queue_size, iommu_hack=False) -> str:
        # Build test network parameters

        if iommu_hack:
            iommu = ",iommu_platform=on,disable-modern=off,disable-legacy=on"
        else:
            iommu = ""

        test_net_config = ''
        if net_type == Interface.BRIDGE or net_type == Interface.BRIDGE_VHOST:
            if BRIDGE_QUEUES == 0:
                queues = ""
                multi_queue = ""
            else:
                queues = f",queues={BRIDGE_QUEUES}"
                multi_queue = ",mq=on"
            if net_type == Interface.BRIDGE_VHOST:
                vhost = True

            test_net_config = (
                f" -netdev tap,vhost={'on' if vhost else 'off'}," +
                f'id=test0,ifname={MultiHost.iface_name(self.test_tap, vm_number)},script=no,' +
                f'downscript=no' +
                queues +
                f' -device virtio-net-{dev_type},id=testif,' +
                f'netdev=test0,mac={MultiHost.mac(self.guest_test_iface_mac, vm_number)}' +
                multi_queue +
                (',use-ioregionfd=true' if ioregionfd else '') +
                (f',rx_queue_size={rx_queue_size},tx_queue_size={tx_queue_size}' if rx_queue_size != -1 and tx_queue_size != -1 else '') +
                iommu
            )
        if net_type == Interface.BRIDGE_E1000:
            test_net_config = (
                f" -netdev tap," +
                f'id=test0,ifname={MultiHost.iface_name(self.test_tap, vm_number)},script=no,' +
                'downscript=no' +
                f' -device e1000,' +
                f'netdev=test0,mac={MultiHost.mac(self.guest_test_iface_mac, vm_number)}' +
                iommu
            )
        elif net_type == Interface.MACVTAP:
            test_net_config = (
                f" -netdev tap,vhost={'on' if vhost else 'off'}," +
                'id=test0,fd=3 3<>/dev/tap$(cat ' +
                f'/sys/class/net/{self.test_macvtap}/ifindex) ' +
                f' -device virtio-net-{dev_type},id=testif,' +
                'netdev=test0,mac=$(cat ' +
                f'/sys/class/net/{self.test_macvtap}/address)' +
                (',use-ioregionfd=true' if ioregionfd else '') +
                (f',rx_queue_size={rx_queue_size},tx_queue_size={tx_queue_size}' if rx_queue_size != -1 and tx_queue_size != -1 else '') +
                    iommu
            )
        elif net_type == Interface.VFIO:
            test_net_config = f' -device vfio-pci,host={self.test_iface_addr}'
        elif net_type.needs_vmux():
            test_net_config = \
                f' -device vfio-user-pci,socket={MultiHost.vfu_path(self.vmux_socket_path, vm_number)}'
        elif net_type.is_vhost_user():
            test_net_config = (
                f" -chardev socket,id=char1,path={MultiHost.vhost_user_sock(vm_number)}" +
                f" -netdev type=vhost-user,id=hostnet1,chardev=char1" +
                f" -device virtio-net-pci,netdev=hostnet1,id=net1,mac={self.guest_test_iface_mac}"
            )
        return test_net_config


    def run_unikraft(self: 'Host',
                     initrd: str,
                     net_type: Interface,
                     vm_log_path: str = '',
                     qemu_build_dir: str = None,
                    ) -> None:
        vm_number = 0
        project_root = str(Path(self.project_root)) # nix wants nicely formatted paths

        cpus = self.guest_vcpus
        mem = self.guest_memory
        vhost = net_type.is_vhost()
        dev_type = 'pci'
        qemu_bin_path = 'qemu-system-x86_64'
        if qemu_build_dir:
            qemu_bin_path = path_join(qemu_build_dir, qemu_bin_path)
        unikraft_bin = f'{project_root}/.unikraft/build/click_qemu-x86_64'

        nix_shell = f"nix shell --inputs-from {project_root} nixpkgs#numactl --command"
        numactl = f"numactl -C {self.cpupinner.qemu(vm_number)}"

        admin_interface = '' + \
            f' -netdev tap,vhost=on,id=admin0,ifname={MultiHost.iface_name(self.admin_tap, vm_number)},' + \
            'script=no,downscript=no' + \
            f' -device virtio-net-{dev_type},id=admif,netdev=admin0,' + \
            f'mac={MultiHost.mac(self.guest_admin_iface_mac, vm_number)}'

        test_net_config = self._test_network_qemu_args(net_type, ioregionfd=False, vhost=vhost, dev_type=dev_type, vm_number=vm_number, rx_queue_size=256, tx_queue_size=256)

        vm_logging = ''
        if vm_log_path != '':
            vm_logging = '' + \
                f' -chardev stdio,id=char0,mux=on,logfile={vm_log_path},signal=off' + \
                ' -serial chardev:char0' + \
                ' -mon chardev=char0'


        self.tmux_new(
            MultiHost.enumerate('qemu', vm_number),
            f"sudo {nix_shell} {numactl} " +
            qemu_bin_path +
            f' -accel kvm' +
            ' -cpu host' +
            f' -smp {cpus}' +
            # shared memory
            f' -m {mem}' +
            self._memory_backend(mem, vm_number) +
            # boot unikraft
            " -append \\\" vfs.fstab=['initrd0:/:extract::ramfs=1:'] --\\\"" +
            f' -kernel {unikraft_bin}' +
            f' -initrd {initrd}' +
            # networking
            test_net_config +
            admin_interface +
            # optional logging
            vm_logging +
            # final remarks
            ' -nographic' +
            # ''
            f' 2>/tmp/trace-vm{vm_number}.log'
            )
        pass


    def kill_unikraft(self: 'Host') -> None:
        self.tmux_kill('qemu')


    def start_vmux(self: 'Host', interface: Interface, num_vms: int = 0) -> None:
        """
        Start vmux in a tmux session. Blocks until vmux is started.

        Parameters
        ----------

        Returns
        -------
        """
        args = ""
        dpdk_args = ""
        vmux_mode = ""
        vmux_socket = f"{self.vmux_socket_path}"
        if interface.is_passthrough():
            # num_vms is also vm_number, because with passthrough there is only one
            vmux_socket = f"{MultiHost.vfu_path(self.vmux_socket_path, num_vms)}"
            args = f' -s {vmux_socket} -d {self.test_iface_addr}'
        if interface in [ Interface.VMUX_DPDK, Interface.VMUX_DPDK_E810, Interface.VMUX_MED ]:
            dpdk_args += f" -u -- -l {self.cpupinner.vmux_main()}"
        if interface.guest_driver() == "ice":
            vmux_mode = "emulation"
        elif interface.guest_driver() == "e1000":
            vmux_mode = "e1000-emu"
        if interface == Interface.VMUX_MED:
            vmux_mode = "mediation"
        if not interface.is_passthrough():
            if num_vms == 0:
                args = f' -s {vmux_socket} -d none -t {MultiHost.iface_name(self.test_tap, 0)} -m {vmux_mode} -e {self.cpupinner.vmux_rx(1)} -f {self.cpupinner.vmux_runner(1)}'
            else:
                for vm_number in MultiHost.range(num_vms):
                    vmux_socket = f"{MultiHost.vfu_path(self.vmux_socket_path, vm_number)}"
                    args += f' -s {vmux_socket} -d none -t {MultiHost.iface_name(self.test_tap, vm_number)} -m {vmux_mode} -e {self.cpupinner.vmux_rx(vm_number)} -f {self.cpupinner.vmux_runner(vm_number)}'

        base_mac = MultiHost.mac(self.guest_test_iface_mac, 1) # vmux increments macs itself
        project_root = str(Path(self.project_root) / "../..") # nix wants nicely formatted paths
        nix_shell = f"nix shell --inputs-from {project_root} nixpkgs#numactl --command"
        # numactl = "numactl -C 1-5 "
        numactl = ""
        self.tmux_new(
            'vmux',
            f'ulimit -n 4096; sudo {nix_shell} {numactl} {self.vmux_path} -q -b {base_mac}'
            f'{args}'
            f'{dpdk_args}'
            # f' -d none -t tap-okelmann02 -m e1000-emu -s /tmp/vmux-okelmann.sock2'
            f'; sleep 999'
        )
        # give vmux some time to start up and create the socket
        self.wait_for_success(f"[[ -S {vmux_socket} ]]")
        self.exec(f'sudo chmod 777 {vmux_socket} || true')
        sleep(10)

    def stop_vmux(self: 'Host') -> None:
        """
        Stop vmux.

        Parameters
        ----------

        Returns
        -------
        """
        self.tmux_kill('vmux')

    def start_pktgen_vhost(self: 'Host', connect_to_vpp: bool = False) -> None:
        vm_number = 0
        if connect_to_vpp:
            vhost_sock = MultiHost.vhost_user_sock('loadgen')
            vdev = f"--vdev 'net_virtio_user0,path={vhost_sock},speed=100000' --single-file-segments"
        else:
            vhost_sock = MultiHost.vhost_user_sock(vm_number)
            vdev = f"--vdev 'eth_vhost0,iface={vhost_sock}'"
            self.exec(f"sudo rm {vhost_sock} || true") # only clean socket if we create it
        # self.tmux_new("pktgen", f"sudo pktgen -l 6,7,8,9 --vdev 'eth_vhost0,iface={vhost_sock}' -- -m '[0:3].0'") #  -G")
        cpus, mapping = self.cpupinner.pktgen()
        self.tmux_new("pktgen", f"sudo pktgen {vdev} -l{cpus} -- -m '{mapping}' -G; sleep 999")
        # known good:  sudo pktgen --vdev 'net_virtio_user0,path=/tmp/vhost-user-okelmann.loadgen' -l0,1,2,3 --single-file-segments -- -m '1.0' -G
        # ptyhon runs: sudo pktgen --vdev 'net_virtio_user0,path=/tmp/vhost-user-okelmann.loadgen' --single-file-segments -l0,1,2,3 -- -m '1.0' -G
        # vdevs = []
        # for vm_number in MultiHost.range(num_vms):
        #     vhost_sock = MultiHost.vhost_user_sock(vm_number)
        #     self.exec(f"sudo rm {vhost_sock} || true")
        #     vdevs += [f"--vdev 'eth_vhost{vm_number},iface={vhost_sock}'"]
        # self.tmux_new("pktgen", f"sudo pktgen --vdev 'eth_vhost0,iface={vhost_sock}' -l{cpus} -- -m '{mapping}' -G")

    def start_pktgen_kni(self: 'Host', kni_name: str) -> None:
        vdev = f"--no-pci --vdev=net_af_packet0,iface={kni_name}"
        cpus, mapping = self.cpupinner.pktgen()
        self.tmux_new("pktgen", f"sudo pktgen {vdev} -l{cpus} -- -m '{mapping}' -G; sleep 999")

    def stop_pktgen_vhost(self: 'Host') -> None:
        self.tmux_kill("pktgen")

    def exec_pktgen(self: 'Host', lua_command: str, workdir: str = None) -> str:
        """
        call like: print(host.exec_pktgen('printf("asdfasdfasdf\\n")'))
        Take care to escape single quotes and backslashes for the shell this will travel thorugh.
        """
        workdir = workdir if workdir else self.project_root
        script = f"""
            package.path = package.path .. ";{workdir}/pybench/Pktgen.lua;"
            require "Pktgen"
            {lua_command}
        """
        # socat_bin = "/nix/store/b3gm6nv28zw2jr0xkbf31xj5mkm56axl-socat-1.8.0.3/bin/socat1"
        socat_bin = "socat"
        output = self.exec(f"echo '{script}' | {socat_bin} - TCP4:localhost:22022")
        return output

    def cleanup_network(self: 'Host', number_vms: int = MAX_VMS) -> None:
        """
        Cleanup the network setup.
        """
        try:
            self.stop_vmux()
            self.stop_vpp()
        except:
            pass

        self.modprobe_test_iface_drivers()
        self.release_test_iface()
        self.stop_xdp_reflector(self.test_iface)
        self.destroy_test_br_tap()
        self.destroy_test_macvtap()
        # TODO destroy admin interfaces!


class Guest(Server):
    """
    Guest class.

    This class represents a guest, so the VM run on the host.

    See Also
    --------
    Server : The Server class.
    Host : The Host class.
    LoadGen : The LoadGen class.

    Examples
    --------
    >>> Guest('server.test.de')
    Guest(fqdn='server.test.de')
    """
    test_iface_ip_net: Optional[str]

    def __init__(self: 'Guest',
                 fqdn: str,
                 test_iface: str,
                 test_iface_addr: str,
                 test_iface_mac: str,
                 test_iface_ip_net: Optional[str],
                 test_iface_driv: str,
                 test_iface_dpdk_driv: str,
                 tmux_socket: str,
                 moongen_dir: str,
                 moonprogs_dir: str,
                 xdp_reflector_dir: str,
                 ssh_config: Optional[str] = None,
                 ssh_as_root: bool = False) -> None:
        """
        Initialize the Guest class.

        Parameters
        ----------
        fqdn : str
            The fully qualified domain name of the guest.
        test_iface : str
            The name of the test interface.
        test_iface_addr : str
            The IP address of the test interface.
        test_iface_mac : str
            The MAC address of the test interface.
        test_iface_driv : str
            The driver of the test interface.
        test_iface_dpdk_driv : str
            The DPDK driver of the test interface.
        tmux_socket : str
            The name for the tmux socket.
        moongen_dir : str
            The directory of the MoonGen installation.
        moonprogs_dir : str
            The directory with the MoonGen Lua programs.
        xdp_reflector_dir : str
            The directory of the XDP Reflector installation.
        localhost : bool
            True if the host is localhost.
        ssh_config : Optional[str]
            Path to local ssh config to use to connect with.

        Returns
        -------
        Guest : The Guest object.

        See Also
        --------
        Server : The Server class.
        Server.__init__ : Initialize the Server class.

        Examples
        --------
        >>> Guest('server.test.de')
        Guest(fqdn='server.test.de')
        """
        super().__init__(fqdn, test_iface, test_iface_addr, test_iface_mac,
                         test_iface_driv, test_iface_dpdk_driv,
                         tmux_socket, moongen_dir, moonprogs_dir,
                         xdp_reflector_dir, ssh_config=ssh_config,
                         ssh_as_root=ssh_as_root)
        self.test_iface_ip_net = test_iface_ip_net

    def __post_init__(self: 'Guest') -> None:
        """
        Post initialization.

        This method is called after the object is created.

        Parameters
        ----------

        Returns
        -------

        See Also
        --------
        __init__ : Initialize the object.
        """
        super().__post_init__()

        # Due to the write lock issue with the /nix/store we cannot do
        # stuff like opening nix shells. So we make sure the guest can
        # run commands without that, and therefore unset the nixos
        # attribute.
        self.nixos = False

    def multihost_clone(self: 'Guest', vm_number: int) -> 'Guest':
        guest = copy.deepcopy(self)
        guest.fqdn = MultiHost.ssh_hostname(guest.fqdn, vm_number)
        if guest.test_iface_ip_net is not None:
            guest.test_iface_ip_net = MultiHost.ip(guest.test_iface_ip_net, vm_number)
        return guest

    def setup_test_iface_ip_net(self: 'Guest'):
        """
        Assign ip address and netmask to the test interface if it exists.

        Parameters
        ----------

        Returns
        -------
        """
        # sometimes the VM needs a bit of extra time until it can assign an IP
        self.wait_for_success(f'sudo ip address add {self.test_iface_ip_net} dev {self.test_iface} 2>&1 | tee /tmp/foo')
        self.exec(f'sudo ip link set {self.test_iface} up')

    def start_iperf_server(self, server_hostname: str):
        """
        Starts an iperf server listening on port "port". Returns the ip address the server is bound to.
        """

        self.tmux_new("iperf3-server", f"iperf3 -s --bind {server_hostname}")


    def stop_iperf_server(self):
        """
        Kills the iperf server process
        """
        self.tmux_kill("iperf3-server")

    # def exec_pktgen(self: 'Guest', lua_command: str) -> str:
    #     Host.exec_pktgen(self, lua_command, workdir=self.project_root)
    def exec_pktgen(self: 'Host', lua_command: str, workdir: str = None) -> str:
        """
        call like: print(host.exec_pktgen('printf("asdfasdfasdf\\n")'))
        Take care to escape single quotes and backslashes for the shell this will travel thorugh.
        """
        workdir = workdir if workdir else self.project_root
        lua_command = lua_command.replace('"', '\\"')
        # socat_bin = "/nix/store/b3gm6nv28zw2jr0xkbf31xj5mkm56axl-socat-1.8.0.3/bin/socat1"
        socat_bin = "socat"
        script = f"""
            {{
            echo "package.path = package.path .. \\";{workdir}/pybench/Pktgen.lua;\\""
            echo "require \\"Pktgen\\""
            echo "{lua_command}"
            }} | {socat_bin} - TCP4:localhost:22022
        """
        output = self.exec(script)
        # output = self.exec(f"echo '{script}' | {socat_bin} - TCP4:localhost:22022")
        return output

class LoadGen(Server):
    """
    LoadGen class.

    This class represents a loadgen server, so the server that runs the load
    generator against the host and guest.

    See Also
    --------
    Server : The Server class.
    Host : The Host class.
    Guest : The Guest class.

    Examples
    --------
    >>> LoadGen('server.test.de')
    LoadGen(fqdn='server.test.de')
    """
    test_iface_ip_net: Optional[str]

    def __init__(self: 'LoadGen',
                 fqdn: str,
                 test_iface: str,
                 test_iface_addr: str,
                 test_iface_mac: str,
                 test_iface_ip_net: Optional[str],
                 test_iface_driv: str,
                 tmux_socket: str,
                 moongen_dir: str,
                 moonprogs_dir: str,
                 xdp_reflector_dir: Optional[str] = None,
                 localhost: bool = False,
                 ssh_config: Optional[str] = None,
                 ssh_as_root: bool = False,
                 **_kwargs) -> None:
        """
        Initialize the LoadGen class.

        Parameters
        ----------
        fqdn : str
            The fully qualified domain name of the load generator.
        test_iface : str
            The name of the test interface.
        test_iface_addr : str
            The IP address of the test interface.
        test_iface_mac : str
            The MAC address of the test interface.
        test_iface_driv : str
            The driver of the test interface.
        tmux_socket : str
            The name for the tmux socket.
        moongen_dir : str
            The directory of the MoonGen installation.
        moonprogs_dir : str
            The directory with the MoonGen Lua programs.
        xdp_reflector_dir : str
            The directory of the XDP Reflector installation.
        localhost : bool
            True if the host is localhost.
        ssh_config : Optional[str]
            Path to local ssh config to use to connect with.

        Returns
        -------
        LoadGen : The LoadGen object.

        See Also
        --------
        Server : The Server class.
        Server.__init__ : Initialize the Server class.

        Examples
        --------
        >>> LoadGen('server.test.de')
        LoadGen(fqdn='server.test.de')
        """
        super().__init__(fqdn, test_iface, test_iface_addr, test_iface_mac,
                         test_iface_driv, tmux_socket, moongen_dir,
                         moonprogs_dir, xdp_reflector_dir, localhost,
                         ssh_config=ssh_config, ssh_as_root=ssh_as_root)
        self.test_iface_ip_net = test_iface_ip_net

    @staticmethod
    def run_l2_load_latency(server: Server,
                            mac: str,
                            srcIp: str = "10.0.0.1",
                            dstIp: str = "10.0.0.2",
                            srcPort: int = 2,
                            dstPort: int = 3,
                            rate: int = 10000,
                            runtime: int = 60,
                            size: int = 60,
                            nr_macs: int = 0,
                            nr_ethertypes: int = 0,
                            histfile: str = '/tmp/histogram.csv',
                            statsfile: str = '/tmp/throughput.csv',
                            outfile: str = '/tmp/output.log'
                            ):
        """
        Run the MoonGen L2 load latency test.

        Parameters
        ----------
        mac : str
            The MAC address of the destination device.
        rate : int
            The rate of the test in Mbps.
        runtime : int
            The runtime of the test in seconds.
        size : int
            The size of the packets in bytes.
        histfile : str
            The path of the histogram file.
        statsfile: str
            The path of the csv file with a throughput time series.
        outfile : str
            The path of the log output file.

        Returns
        -------

        See Also
        --------

        Example
        -------
        >>> LoadGen('server.test.de').start_l2_load_latency()
        """
        server.tmux_new('loadlatency', f'cd {server.moongen_dir}; ' +
                      'sudo bin/MoonGen '
                      f'{server.project_root}/benchmark/configurations/l2-load-latency.lua ' +
                      f'-r {rate} -f {histfile} -T {runtime} -s {size} ' +
                      f' -c {statsfile} -m {nr_macs} -e {nr_ethertypes} ' +
                      f'--srcIp {srcIp} --dstIp {dstIp} ' +
                      f'--srcPort {srcPort} --dstPort {dstPort} ' +
                      f'{server._test_iface_id} {mac} ' +
                      f'2>&1 | tee {outfile}; echo TEST_DONE >> {outfile}; sleep 999')

    @staticmethod
    def stop_l2_load_latency(server: 'Server'):
        """
        Stop the MoonGen L2 load latency test.

        Parameters
        ----------

        Returns
        -------
        """
        server.tmux_kill('loadlatency')

    @staticmethod
    def start_wrk2(server: 'Server', url: str, script_path: str, duration: int = 11, rate: int = 10, connections: int = 16, threads: int = 8, outfile: str = "/tmp/outfile.log", workdir: str ="./"):
        docker_cmd = f'docker run -ti --mount type=bind,source=./wrk2,target=/wrk2 --network host wrk2d'
        wrk_cmd = f'wrk -D exp -t {threads} -c {connections} -d {duration} -L -s {script_path} http://{url} -R {rate}'
        server.tmux_new('wrk2', f'cd {workdir}; ' +
                        f'{docker_cmd} {wrk_cmd} 2>&1 | tee {outfile}; echo AUTOTEST_DONE >> {outfile}; sleep 999');

    @staticmethod
    def stop_wrk2(server: 'Server'):
        server.tmux_kill('wrk2')

    def start_redis(self, nr: int = 0):
        project_root = str(Path(self.project_root) / "../..") # nix wants nicely formatted paths
        port = 6379 + nr
        redis_cmd = f'redis-server --port {port} --protected-mode no --save ""'
        nix_cmd = f"nix shell --inputs-from {project_root} nixpkgs#redis --command {redis_cmd}"
        #alternative: NIXPKGS_ALLOW_UNFREE=1 nix shell --impure github:nixos/nixpkgs/109e13db243249e26b8b8d861424578400aae882#dragonflydb; dragonfly --port 6379 --logtostderr --dbfilename /tmp/foo
        self.tmux_new(f"redis{nr}", f"{nix_cmd}; sleep 999")
        return port


    def stop_redis(self, nr: int = 0):
        self.tmux_kill(f"redis{nr}")

    def setup_test_iface_ip_net(self: 'LoadGen'):
        """
        Assign ip address and netmask to the test interface if it exists.

        Parameters
        ----------

        Returns
        -------
        """
        self.exec(f'sudo ip link set {self.test_iface} up')
        self.exec(f'sudo ip address add {self.test_iface_ip_net} dev {self.test_iface}')


    def run_iperf_client(self, runtime: int, server_hostname: str, output_path: str, tmp_out_path: str, direction: str = "forward", proto: str = "tcp", length: int = -1, vm_num = ""):
        """
        Starts iperf client
        length: default if -1
        """

        options = ""

        options += "-J"

        if direction  == "reverse":
            options += " -R"
        elif direction == "bidirectional":
            options += " --bidir"
        elif direction != "forward":
            warning(f"Unknown direction \"{direction}\". Using forward direction")

        if length != -1:
            options += f" -l {length}"

        if proto == "udp":
            options += " -u -b 0"
        elif proto != "tcp":
            warning(f"Unknown protocol {proto}. Using tcp.")

        info("Starting iperf client on " + server_hostname)
        self.tmux_new(f"iperf3-client{vm_num}", f"iperf3 -c {server_hostname} -t {runtime} {options} | tee {tmp_out_path}; cp {tmp_out_path} {output_path}; sleep 999")


    def stop_iperf_client(self, vm_num = ""):
        self.tmux_kill(f"iperf3-client{vm_num}")

    def start_ptp4l(self, software_ts=False):
        self.tmux_new("ptp4l", f"sudo {self._Server__cmd_with_package('linuxptp')} ptp4l -i {self.test_iface} -m -E -2 { '-S' if software_ts else '' }")

    def stop_ptp4l(self):
        self.tmux_kill("ptp4l")
