# -*- coding: utf-8 -*-

# _wallet is implemented in ./src_ext
# technically we can implement everything in python but use C module to
# reuse the existing code; it's also easy to prototype low-level code
import _wallet as _w

import os
from pathlib import Path
from typing import TypeAlias, List, Tuple, Dict, Any

FileName: TypeAlias = str | os.PathLike


class Wallet:
    def __init__(self):
        self.fd = None
        pass

    def open_device(self, path: FileName = "/dev/vmpl_device") -> int:
        self.fd = _w.monitor_connect()
        if self.fd < 0:
            raise Exception(f"Failed to open {path}, forgot to load the kernel module?")
        return self.fd

    def close_device(self) -> None:
        if self.fd:
            _w.monitor_close()
            self.fd = None

    def create_zygote(
        self, zygote: FileName, manifest: FileName, libos: FileName
    ) -> int:
        if not Path(zygote).exists():
            raise Exception(f"Zygote {zygote} not found")
        if not Path(manifest).exists():
            raise Exception(f"Manifest {manifest} not found")
        if not Path(libos).exists():
            raise Exception(f"LibOS {libos} not found")
        zygote_id = _w.create_zygote(zygote, manifest, libos)
        if zygote_id < 0:
            raise Exception(f"Failed to create zygote {zygote}")
        return Zygote(zygote_id)

    def attest_monitor(self) -> str:
        if not self.fd:
            raise Exception("Cannot attest monitor - not initialized!")
        return _w.attest_monitor()

    # helper functions for attestation microbenchmarks
    def measure_monitor_cold(self):
        if not self.fd:
            raise Exception("Cannot measure monitor - not initialized!")
        return _w.measure_monitor_cold()

    def measure_monitor_hot(self):
        if not self.fd:
            raise Exception("Cannot measure monitor - not initialized!")
        return _w.measure_monitor_hot()
    # end of helper functions for attestation microbenchmarks

    def __enter__(self):
        if not self.fd:
            self.open_device()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close_device()


class TrustedProcess:
    def __init__(self, process_id):
        self.process_id = process_id

class Trustlet(TrustedProcess):
    def __init__(self, process_id):
        TrustedProcess.__init__(self, process_id)

    def invoke_trustlet(self, argument: str, output_size: int) -> str:
        ret = _w.invoke_trustlet(self.process_id, argument, output_size)
        return ret

    def attest_execution(self, input: str, input_len: int, output: str, output_len: int) -> str:
        ret = _w.attest_execution(self.process_id, input, input_len, output, output_len)
        return ret

    # helper functions for attestation microbenchmarks
    def prepare_measure_trustlet_cold(self):
        _w.prepare_measure_trustlet_cold(self.process_id)
        return

    def measure_trustlet_cold(self):
        _w.measure_trustlet_cold(self.process_id)
        return

    def measure_trustlet_hot(self):
        _w.measure_trustlet_hot(self.process_id)
        return

    def measure_function(self, input: str, input_len: int, output: str, output_len: int):
        _w.measure_function(self.process_id, input, input_len, output, output_len)
        return
    # end of helper functions for attestation microbenchmarks

class Zygote(TrustedProcess):
    def __init__(self, process_id):
        TrustedProcess.__init__(self, process_id)

    def create_trustlet(self, function_code: FileName) -> Trustlet:
        if not Path(function_code).exists():
            raise Exception(f"Function Code {function_code} not found")
        with open(function_code, mode='r') as file:
            function_code = file.read()
        trustlet_id = _w.create_trustlet(self.process_id, function_code)
        if trustlet_id < 0:
            raise Exception(f"Failed to create trustlet")
        return Trustlet(trustlet_id)

    # helper functions for attestation microbenchmarks
    def prepare_measure_zygote_cold(self):
        _w.prepare_measure_zygote_cold(self.process_id)
        return

    def measure_zygote_cold(self):
        _w.measure_zygote_cold(self.process_id)
        return

    def measure_zygote_hot(self):
        _w.measure_zygote_hot(self.process_id)
        return
    # end of helper functions for attestation microbenchmarks

