from dataclasses import dataclass, fields as dataclass_fields
from util import safe_cast, product_dict, randomword
from typing import Iterator, cast, List, Dict, Callable, Tuple, Any, Self, TypeVar, Iterable, Type, Generic
from os.path import isfile, join as path_join, basename
import os
from abc import ABC, abstractmethod
from server import Host, Guest, LoadGen
import autotest as autotest
from configparser import ConfigParser
from argparse import (ArgumentParser, ArgumentDefaultsHelpFormatter, Namespace,
                      FileType, ArgumentTypeError)
from typing import Tuple, Iterator, Any, Dict, Callable
from contextlib import contextmanager, ContextDecorator
from enums import Machine, Interface, Reflector, MultiHost
from logging import (info, debug, error, warning,
                     DEBUG, INFO, WARN, ERROR)
from util import safe_cast, deduplicate
from pathlib import Path
import copy
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
import subprocess
from conf import G
from tqdm import tqdm
from tqdm.contrib.telegram import tqdm as tqdm_telegram
import getpass
from root import TEST_ROOT

NUM_WORKERS = 8 # with 16, it already starts failing on rose

def setup_parser() -> ArgumentParser:
    """
    Creates ArgumentParser instance for parsing program options
    """

    # create the argument parser
    parser = ArgumentParser(
        description='''
        Foobar.''',
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    # define all the arguments
    parser.add_argument('-c',
                        '--config',
                        default=f'{TEST_ROOT}/hosts/localhost.cfg',
                        type=FileType('r'),
                        help='Configuration file path',
                        )
    parser.add_argument('-o',
                        '--outdir',
                        default='/tmp/out1',
                        help='Directory to expect old results in and write new ones to',
                        )
    parser.add_argument('-b',
                        '--brief',
                        action='store_true',
                        help='Run a limited set of tests that run faster. (disable incremental, deletes output folder first)',
                        )
    parser.add_argument('-v',
                        '--verbose',
                        dest='verbosity',
                        action='count',
                        default=2,
                        help='''Verbosity, can be given multiple times to set
                             the log level (0: error, 1: warn, 2: info, 3:
                             debug)''',
                        )
    parser.add_argument('-q',
                        '--quiet',
                        action='count',
                        default=0,
                        help='''Reduce verbosity. -q sets verbosity to 1
                             (warn), -qq sets it to 0 (error).''',
                        )
    return parser


def add_test_arguments(parser: ArgumentParser, test_cls: Type['AbstractBenchTest']) -> None:
    """
    Add an argparse argument for each field of a dataclass that inherits AbstractBenchTest.

    Each argument accepts one or more values (nargs='+'), suitable for building test matrices.
    The argument type is inferred from the dataclass field's type annotation.

    Example:
        parser = setup_parser()
        add_test_arguments(parser, PktgenTest)
        args = parser.parse_args()
        # args.batchsize = [1, 32], args.workload = [0, 50], ...
    """
    from typing import get_type_hints
    hints = get_type_hints(test_cls)
    for field in dataclass_fields(test_cls):
        field_type = hints[field.name]
        parser.add_argument(
            f'--{field.name}',
            nargs='+',
            type=field_type,
            default=None,
            help=f'Set to not None to override {field.name} values ({field_type.__name__})',
        )


def test_matrix_from_args(args: Namespace, test_cls: Type['AbstractBenchTest'],
                          defaults: Dict[str, List[Any]] = {}) -> Dict[str, List[Any]]:
    """
    Build a test_matrix dict from parsed arguments.

    For each field of test_cls, uses the value from args if provided,
    otherwise falls back to defaults.

    Example:
        defaults = dict(repetitions=[1], batchsize=[1, 32], ...)
        matrix = test_matrix_from_args(args, PktgenTest, defaults)
        tests = PktgenTest.list_tests(matrix)
    """
    matrix = {}
    for field in dataclass_fields(test_cls):
        value = getattr(args, field.name, None)
        if value is not None:
            matrix[field.name] = value
            warning(f"Overriding {test_cls.__name__}.{field.name} with command line argument: {value}")
        elif field.name in defaults:
            matrix[field.name] = defaults[field.name]
    return matrix


def setup_host_interface(host: Host, interface: Interface, vm_range: range = range(0)) -> None:
    autotest.LoadLatencyTestGenerator.setup_interface(host, Machine.PCVM, interface, vm_range=vm_range)


def end_foreach(guests: Dict[int, Guest], func: Callable[[int, Guest], None], workers: int = NUM_WORKERS):
    """
    Example usage:
        def foreach_parallel(i, guest): # pyright: ignore[reportGeneralTypeIssues]
            guest.exec(f"docker-compose up")
        end_foreach(guests, foreach_parallel)
    """
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(func, i, guest) for i, guest in guests.items()]
        for future in futures:
            future.result()  # Waiting for all tasks to complete


@dataclass
class Measurement:
    args: Namespace
    config: ConfigParser
    test_type: None|Type['AbstractBenchTest']

    supports_boot_only: bool
    initialized_vms: Dict[int, bool] # vm_number -> vm started but not initialized OR vm started and initialized

    host: Host
    guest: Guest
    loadgen: LoadGen

    guests: Dict[int, Guest]  # for multihost VMs we start counting VMs at 1


    def __init__(self, test_type: None|Type['AbstractBenchTest'] = None, supports_boot_only: bool = False):
        parser: ArgumentParser = setup_parser()
        self.test_type = test_type
        if test_type is not None:
            add_test_arguments(parser, test_type)

        self.supports_boot_only = supports_boot_only
        self.initialized_vms = dict()
        if self.supports_boot_only:
            parser.add_argument('--boot-only',
                                action='store_true',
                                help='Only start the VM and initialize it, but dont run benchmarks.',
                                )


        self.args: Namespace = autotest.parse_args(parser)
        self.args.verbosity = max(0, self.args.verbosity - self.args.quiet)
        autotest.setup_logging(self.args)
        self.config: ConfigParser = autotest.setup_and_parse_config(self.args)

        host, guest, loadgen = autotest.create_servers(self.config).values()
        self.host = safe_cast(Host, host)
        self.guest = safe_cast(Guest, guest)
        self.loadgen = safe_cast(LoadGen, loadgen)

        self.host.check_cpu_freq()
        self.loadgen.check_cpu_freq()

        self.guests = dict()

        G.OUT_DIR = self.args.outdir
        G.BRIEF = self.args.brief

        if G.BRIEF:
            subprocess.run(["sudo", "rm", "-r", G.OUT_DIR])


    def apply_cmdline_overrides(self, test_matrix: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        if self.test_type is None:
            return test_matrix
        return test_matrix_from_args(self.args, self.test_type, defaults=test_matrix)

    def mark_vm_initialized(self, vm_number: int):
        if vm_number in self.initialized_vms:
            self.initialized_vms[vm_number] = True
        else:
            error(f"Trying to mark VM {vm_number} as initialized, but it was not started yet.")

        if len(self.initialized_vms.values()) > 0 and all(self.initialized_vms.values()):
            info("All VMs initialized")
            if getattr(self.args, "boot_only", False):
                breakpoint()
                pass


    def hosts(self) -> Tuple[Host, LoadGen]:
        return (self.host, self.loadgen)


    @staticmethod
    def estimated_boottime(num_vms: int) -> float:
        """
        estimated time to boot this system in seconds
        """
        # time taken to boot a batch of VMs (2min each)
        # min(factor for 1 VM, factor for more VMs)
        vm_boot = max(0.3, (num_vms / 32)) * 60 * 2
        return vm_boot

    @contextmanager
    def unikraft_vm(self, interface: Interface, click_config: str, vm_log: str = "", run_guest_args = dict(), cpio_files: List[str] = []) -> Iterator[Guest]:
        """
        Creates a unikraft-click virtual machine
        """
        assert not self.supports_boot_only, "Measurement.unikraft_vm() does not support the boot-only flag."

        # host: inital cleanup

        debug('Initial cleanup')
        try:
            self.host.kill_unikraft()
        except Exception:
            pass

        self.host.cleanup_network()

        # host: set up interfaces and networking

        self.host.detect_test_iface()

        info(f"Setting up interface {interface.value}")
        setup_host_interface(self.host, interface)

        # network sidecars
        if interface.needs_vmux():
            self.host.start_vmux(interface)
        if interface.needs_vpp():
            self.host.start_vpp()

        # prepare initrd

        tmpdir = f"/tmp/measure-cpio-{randomword(6)}"
        initrd = f"{tmpdir}.cpio"
        self.host.exec(f"sudo rm -r {tmpdir} || true")
        self.host.exec(f"sudo rm {initrd} || true")
        self.host.exec(f"mkdir -p {tmpdir}")
        with open("/tmp/config.click", "w") as text_file:
            text_file.write(click_config)
        self.host.copy_to("/tmp/config.click", f"{tmpdir}/config.click")
        for cpio_file in cpio_files:
            with open(f"{self.host.project_root}/{cpio_file}", 'rb') as file:
                data = file.read()
                self.host.write(data, f"{tmpdir}/{basename(cpio_file)}")
        self.host.exec(f"{self.host.project_root}/libs/unikraft/support/scripts/mkcpio {initrd} {tmpdir}")

        # start VM

        info(f"Starting unikraft VM ({interface.value})")
        self.host.run_unikraft(
                initrd=initrd,
                net_type=interface,
                vm_log_path=vm_log,
                qemu_build_dir=self.config.get('host', 'qemu_path', fallback=None),
                **run_guest_args
                )

        debug("Waiting for click to start")
        self.host.wait_for_success(f"grep 'Starting driver...' {vm_log}", timeout=40)

        yield self.guest

        # teardown

        self.host.kill_unikraft()
        if interface.needs_vmux():
            self.host.stop_vmux()
        if interface.needs_vpp():
            self.host.stop_vpp()
        self.host.cleanup_network()
        self.host.exec(f"sudo rm -r {tmpdir} || true")
        self.host.exec(f"sudo rm {initrd} || true")

    @contextmanager
    def virtual_machine(self, interface: Interface, run_guest_args = dict()) -> Iterator[Guest]:
        """
        Creates a guest virtual machine
        """

        # host: inital cleanup

        debug('Initial cleanup')
        try:
            self.host.kill_guest()
        except Exception:
            pass

        self.host.cleanup_network()

        # host: set up interfaces and networking

        self.host.detect_test_iface()

        info(f"Setting up interface {interface.value}")
        setup_host_interface(self.host, interface)

        if interface.needs_vmux():
            self.host.start_vmux(interface)
        if interface.needs_vpp():
            self.host.start_vpp()

        # start VM

        info(f"Starting VM ({interface.value})")
        self.host.run_confidential_guest(
                net_type=interface,
                qemu_build_dir=self.config.get('host', 'qemu_path', fallback=None),
                **run_guest_args
                )

        debug("Waiting for guest connectivity")
        self.guest.wait_for_connection(timeout=120)

        self.initialized_vms[0] = False # mark VM 0 as started but not initialized yet

        yield self.guest

        # teardown

        self.host.kill_guest()
        if interface.needs_vmux():
            self.host.stop_vmux()
        if interface.needs_vpp():
            self.host.stop_vpp()
        self.host.cleanup_network()

        del self.initialized_vms[0] # remove VM 0 from initialized_vms


    @contextmanager
    def virtual_machines(self, interface: Interface, num: int = 1, batch: int = 32) -> Iterator[Dict[int, Guest]]:
        # Batching is necessary cause if network setup takes to long, bringing up the interfaces times out, networking is permanently broken and systemds spiral into busy restarting

        # host: inital cleanup

        debug('Initial cleanup')
        self.guests = dict()

        try:
            self.host.kill_guest()

        except Exception as e:
            error("Could not kill guest VMs")
            error(e.with_traceback())
            pass

        self.host.modprobe_test_iface_drivers() # cleanup network needs device drivers
        self.host.cleanup_network() # cleanup unclear for ubpf


        # host: set up interfaces and networking

        self.host.detect_test_iface()

        unbatched_interfaces = [
            interface for interface in Interface.__members__.values() if
                                interface.needs_vfio() or (interface.needs_br_tap() and interface.needs_vmux()) ]

        if interface in unbatched_interfaces:
            # vmux taps need to be there all from the start (no batching)
            info(f"Setting up interface {interface.value} for {num} VMs")
            setup_host_interface(self.host, interface, vm_range=range(1, num+1))

        if interface.needs_vmux():
            self.host.start_vmux(interface, num_vms=num)
        if interface.needs_vpp():
            self.host.start_vpp()

        # start VMs in batches of batch
        range_ = MultiHost.range(num)

        while range_:
            # pop first batch
            vm_range = range_[:batch]
            range_ = range_[batch:]

            info(f"Starting VM {vm_range.start}-{vm_range.stop - 1}")

            if interface not in unbatched_interfaces:
                info(f"Setting up interface {interface.value} for {num} VMs")
                setup_host_interface(self.host, interface, vm_range=vm_range)

            # start VM

            for i in vm_range:
                info(f"Starting VM {i} ({interface.value})")

                # self.host.run_guest(net_type=interface.net_type(), machine_type='pc', qemu_build_dir=QEMU_BUILD_DIR, vm_number=81)
                self.host.run_guest(
                        net_type=interface,
                        machine_type='pc',
                        qemu_build_dir=self.config.get('host', 'qemu_path', fallback=None),
                        vm_number=i
                        )

                self.guests[i] = self.guest.multihost_clone(i)

                # giving each qemu instance time to allocate its memory can help starting more intances.
                # If multiple qemus allocate at the same time, both will fail even though one could have successfully started if it was the only one doing allocations.
                time.sleep(1)

            info(f"Waiting for connectivity of guests")
            for i in vm_range:
                self.guests[i].wait_for_connection(timeout=120)
                self.initialized_vms[i] = False # mark VM i as started but not initialized yet

        yield self.guests

        # teardown

        self.host.kill_guest()
        if interface in [ Interface.VMUX_PT, Interface.VMUX_EMU ]:
            self.host.stop_vmux()
        if interface.needs_vpp():
            self.host.stop_vpp()
        self.host.cleanup_network()

        for i in MultiHost.range(num):
            del self.initialized_vms[i] # remove VM i from initialized_vms


A = TypeVar("A", bound='AbstractBenchTest')

@dataclass
class AbstractBenchTest(ABC):
    # magic parameter: repetitions
    # Feature matrixes for other parameters take lists of values to iterate over.
    # Wile repetitions is also a list in the feature matrix, even single value (e.g. 3) still means that this test will be run 3 times.
    repetitions: int
    num_vms: int # assumed to always be in args_reboot

    @abstractmethod
    def test_infix(self) -> str:
        # example: return f"{self.app}_{self.interface}_{self.num_vms}vms_{self.rps}rps"
        raise Exception("unimplemented")

    @abstractmethod
    def estimated_runtime(self) -> float:
        """
        estimate time needed to run this benchmark excluding boottime in seconds. Return -1 if unknown.
        """
        raise -1

    def output_filepath(self, repetition: int, extension: str = "log"):
        return path_join(G.OUT_DIR, f"{self.test_infix()}_rep{repetition}.{extension}")

    def test_done(self, repetition: int):
        output_file = self.output_filepath(repetition)
        return isfile(output_file)

    def needed(self):
        for repetition in range(self.repetitions):
            if not self.test_done(repetition):
                return True
        return False

    @classmethod
    def list_tests(cls: Type[A], test_matrix: Dict[str, List[Any]], exclude_test = lambda test: False) -> List[A]:
        """
        test_matrix:
        dict where every key corresponds to a constructor parameter/field for this cls/BenchTest (same list as test_parameters() returns).
        Each value is a list of values to be tested.
        """
        ret = []
        for test_args in product_dict(test_matrix):
            test = cls(**test_args)
            if not exclude_test(test):
                ret += [ test ]
        return ret

    @classmethod
    def test_matrix(cls: Type[A], tests: List[A]):
        """
        Generalizes a list of tests into a test matrix.
        Note, that this matrix can be a superset of the original list of tests.
        This can happen for example, if the list is a filtered version of list_tests(), because this sparseness cannot be represented by a test_matrix.
        """
        if len(tests) == 0:
            return dict()

        ret = dict()
        for key in tests[0].__dict__.keys():
            values = []
            for test in tests:
                value = test.__dict__[key]
                if value not in values:
                    values += [ value ]
            ret[key] = values

        return ret

    @classmethod
    def test_matrix_string(cls: Type[A], tests: List[A]) -> str:
        """
        Calls test_matrix() and formats the output nicely.
        """
        test_matrix = cls.test_matrix(tests)

        # calculate sparseness (how many entries in the test matrix are actually in tests)
        num_tests_matrix = 0
        for values in test_matrix.values():
            if num_tests_matrix == 0:
                num_tests_matrix = len(values)
            else:
                num_tests_matrix *= len(values)
        matrix_usage = len(tests) / num_tests_matrix
        sparseness = f"{(1 - matrix_usage)*100:.0f}%"

        dimensions = len(test_matrix.keys())
        if matrix_usage == 1:
            description = f"{dimensions} dimensional feature matrix: "
        else:
            description = f"{dimensions} dimensional feature matrix ({sparseness} sparse): "

        ret = description + "{ \n"
        for key, values in test_matrix.items():
            values = ", ".join([ str(v) for v in values])
            ret += f"  {key}: {values}\n"
        return ret + "}"

    @classmethod
    def any_needed(cls, test_matrix: Dict[str, List[Any]], exclude_test = lambda test: False) -> bool:
        """
        Test matrix: like kwargs used to initialize DeathStarBenchTest, but every value is the list of values.
        """
        for test in cls.list_tests(test_matrix, exclude_test=exclude_test):
            if test.needed():
                debug(f"any_needed: needs {test}")
                return True
        return False

    @staticmethod
    def find_errors(out_dir: str, error_indicators: List[str]) -> bool:
        """
        See if output files match any error_indicator strings
        """
        failure = False
        out = ""
        try:
            for match in error_indicators:
                out = out + "\n" + str(subprocess.check_output(["grep", "-r", match, out_dir]))
        except subprocess.CalledProcessError:
            failure = True

        errors_found = not failure
        if errors_found:
            error(f"Some wrk2 tests returned errors:\n{out}")
        return errors_found

    @classmethod
    def estimate_time(cls, test_matrix: Dict[str, List[Any]], args_reboot: List[str] = []) -> float:
        """
        Test matrix: like kwargs used to initialize DeathStarBenchTest, but every value is the list of values.
        kwargs_reboot: test_matrix keys. Changing these parameters requires a reboot.
        """
        tests = cls.list_tests(test_matrix)
        return cls.estimate_time2(tests, args_reboot=args_reboot, prints=True)

    @classmethod
    def estimate_time2(cls, tests: List[Self], args_reboot: List[str], prints: bool = True) -> float:
        """
        Test matrix: like kwargs used to initialize DeathStarBenchTest, but every value is the list of values.
        kwargs_reboot: test_matrix keys. Changing these parameters requires a reboot.
        tests: if not None, ignore test_matrix
        """
        # usually we check if a test has already been run. Hence we never run the same test twice.
        tests = deduplicate(tests)

        total = 0
        needed = 0
        needed_s = 0.0
        unknown_runtime = False
        tests_needed = []
        for test in tests:
            total += 1
            if test.needed():
                needed += 1
                estimated_runtime = test.estimated_runtime()
                if estimated_runtime == -1:
                    unknown_runtime = True
                needed_s += estimated_runtime
                tests_needed += [ test ]

        # find test parameters that trigger reboots
        reboot_triggers = []
        reboot_tests = []
        for test in tests_needed:
            # only test parameters relevant for reboots
            test_parameters = dict()
            for key in args_reboot:
                test_parameters[key] = test.__dict__[key]
            # append only the first test that triggeres a reboot
            if test_parameters not in reboot_triggers:
                reboot_triggers += [ test_parameters ]
                reboot_tests += [ test ]

        # estimate time needed for reboots
        for trigger, test in zip(reboot_triggers, reboot_tests):
            duration_s = Measurement.estimated_boottime(test.num_vms)
            if "repetitions" in args_reboot:
                duration_s *= test.repetitions
            needed_s += duration_s

        if prints:
            if unknown_runtime:
                info(f"Test not cached yet: {needed}/{total}. Time to completion not known.")
            else:
                info(f"Test not cached yet: {needed}/{total}. Expected time to completion: {needed_s/60:.0f}min ({needed_s/60/60:.1f}h)")

        return needed_s


    @classmethod
    def test_parameters(cls) -> List[str]:
        """
        return the list of names of input parameters for this test
        """
        return [i for i in cls.__match_args__]

T = TypeVar("T", bound=AbstractBenchTest)

class Bench(Generic[T], ContextDecorator):
    tqdm: Any

    def __init__(self, tests: List[T], args_reboot: List[str] = [], brief: bool = False):
        self.args_reboot = args_reboot
        assert len(tests) > 0
        self.remaining_tests = [ test for test in tests if test.needed()]
        self.time_remaining_s = AbstractBenchTest.estimate_time2(self.remaining_tests, args_reboot=self.args_reboot, prints=False)
        self.tqdm_constructor = tqdm
        self.brief = brief
        self.probe_peter()

    def probe_peter(self):
        if not self.brief:
            try:
                with open(f"/home/{getpass.getuser()}/.config/sops-nix/telegram_bot_token", 'r') as file:
                    data = file.read().strip()
                def my_tqdm(*args, **kwargs):
                    return tqdm_telegram(*args, chat_id="272730663", token=data, **kwargs)
                self.tqdm_constructor = my_tqdm
            except Exception:
                pass # leave default tqdm_constructor

    def __enter__(self):
        total_min = (self.time_remaining_s + 0.1) / 60 # +0.1 to avoid float summing errors
        self.tqdm = self.tqdm_constructor(total=total_min,
              unit="min",
              # - cut off float decimals
              # - append newline to print every update to new line (to avoid garbled newlines when we print between progress updates)
              bar_format="{l_bar}{bar}| {n:.0f}/{total:.0f}min [{elapsed}<{remaining}, {rate_fmt}{postfix}]\n",
              )
        return self, self.remaining_tests

    def __exit__(self, *exc):
        self.tqdm.close()

    def iterator(self, tests: List[T], test_parameter: str) -> Iterable[Tuple[Any, List[T]]]:
        """
        Return an iterator over all values of test_parameter of tests.
        test_parameter: name of the parameter (AbstractBenchTest member variable name) to iterate over
        """
        parameter_values = [ test.__dict__[test_parameter] for test in tests ]
        parameter_values = deduplicate(parameter_values)
        for parameter_value in parameter_values:
            parameter_tests = [ test for test in tests if test.__dict__[test_parameter] == parameter_value]
            yield (parameter_value, parameter_tests)


    def multi_iterator(self, tests: List[T], test_parameters: List[str], extremes_only: bool = False) -> Iterable[Tuple[List[Any], List[T]]]:
        """
        Loops over test_parameters (member variables in tests[] objects).

        Like multi_iterator(), but can be used like:
        for [a_param, b_param], tests_ in bench.multi_iterator(tests, ["a", "b"]):
            ...
        """
        for iteration_parameter_dict, iteration_tests in self.multi_iterator_dict(tests, test_parameters, extremes_only=extremes_only):
            iteration_parameters = [ iteration_parameter_dict[parameter_name] for parameter_name in test_parameters ]
            yield (iteration_parameters, iteration_tests)


    def multi_iterator_dict(self, tests: List[T], test_parameters: List[str], extremes_only: bool = False) -> Iterable[Tuple[Dict[str, Any], List[T]]]:
        """
        Can replace nested iterators.

        Example:
        for param_a, a_tests in bench.iterator(tests, "a"):
            for param_b, b_tests in bench.iterator(a_tests, "b"):
                ...
        Replaced with:
        for params, tests_ in bench.multi_iterator(tests, ["a", "b"]):
            param_a = params["a"]
            param_b = params["b"]
            ...
        """
        if len(tests) == 0:
            return

        test_matrix = tests[0].test_matrix(tests)
        loop_matrix = { key: value for (key, value) in test_matrix.items() if key in test_parameters }
        if extremes_only:
            # Reduce each numeric parameter to only [min, max]; keep non-numeric as-is
            def find_extremes(values: List[Any]) -> List[Any]:
                if len(values) <= 1:
                    return values
                if isinstance(values[0], (int, float, complex)):
                    return [ min(values), max(values) ]
                else:
                    return values
            loop_matrix = { key: find_extremes(values) for (key, values) in loop_matrix.items() }
        # from the potential feature matrix, generate a list of all possible parameter combinations
        potential_iterations = product_dict(loop_matrix)
        # track yielded parameter combos to avoid duplicates from snapping (extremes_only)
        seen = set()
        for iteration_parameters in potential_iterations:
            # find all tests that match the parameters of this iteration
            iteration_tests = [ test for test in tests if all(map(lambda kv: test.__dict__[kv[0]] == kv[1], iteration_parameters.items())) ]
            if len(iteration_tests) == 0:
                if not extremes_only:
                    # can happen if the original list does not contain all tests generated by a full feature matrix
                    continue
                # Can happen if the original list does not contain all tests generated by a full feature matrix.
                # Since we want extremes, snap to the most extreme test that does exist:
                # match non-numeric params exactly, then iteratively narrow by snapping
                # each numeric param to the closest available value.
                non_numeric = { k: v for k, v in iteration_parameters.items() if not isinstance(v, (int, float, complex)) }
                numeric = { k: v for k, v in iteration_parameters.items() if isinstance(v, (int, float, complex)) }
                candidates = [ t for t in tests if all(t.__dict__[k] == v for k, v in non_numeric.items()) ]
                if not candidates:
                    continue
                for param, target in numeric.items():
                    available = set(t.__dict__[param] for t in candidates)
                    closest = min(available, key=lambda v: abs(v - target))
                    candidates = [ t for t in candidates if t.__dict__[param] == closest ]
                iteration_tests = candidates
                iteration_parameters = { k: iteration_tests[0].__dict__[k] for k in iteration_parameters }
            if extremes_only:
                # multiple extreme combos can snap to the same existing test; deduplicate
                key = frozenset(iteration_parameters.items())
                if key in seen:
                    continue
                seen.add(key)
            yield (iteration_parameters, iteration_tests)

    def done(self, done: T):
        # TODO make this obsolete: integrate it into iterators and __exit__ or so
        self.remaining_tests = [ test for test in self.remaining_tests if test != done ]
        time_remaining_new_s = AbstractBenchTest.estimate_time2(self.remaining_tests, args_reboot=self.args_reboot, prints=False)
        time_progress_s = self.time_remaining_s - time_remaining_new_s
        self.time_remaining_s = time_remaining_new_s
        self.tqdm.update(time_progress_s / 60)


def main():
    import measure_vm
    import measure_lat

    measurement = Measurement()

    # estimate runtimes
    info("")
    measure_vm.main(measurement, plan_only=True)
    measure_lat.main(measurement, plan_only=True)

    info("Running benchmarks ...")
    info("")
    measure_vm.main(measurement)
    measure_lat.main(measurement)
    error("TODO")

if __name__ == "__main__":
    main()
