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
        self.fd = _w.open_device(path)
        if self.fd < 0:
            raise Exception(f"Failed to open {path}, forgot to load the kernel module?")
        return self.fd

    def close_device(self) -> None:
        if self.fd:
            _w.close_device(self.fd)
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
        zygote_id = _w.create_zygote(self.fd, zygote, manifest, libos)
        if zygote_id < 0:
            raise Exception(f"Failed to create zygote {zygote}")
        self.zyotes.add(zygote_id)
        return zygote_id

    def create_trustlet(self, zygote_id: int, function_code: FileName) -> int:
        if not Path(function_code).exists():
            raise Exception(f"Function Code {function_code} not found")
        trustlet_id = _w.create_trustlet(self.fd, zygote_id, function_code)
        if trustlet_id < 0:
            raise Exception(f"Failed to create trustlet")
        self.trustlets.add(trustlet_id)
        return trustlet_id

    def invoke_trustlet(self, trustlet_id: int, argument: str) -> str:
        ret = _w.invoke_trustlet(self.fd, trustlet_id, argument)
        return ret

    def __enter__(self):
        if not self.fd:
            self.open_device()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close_device()
        self.fd = None
