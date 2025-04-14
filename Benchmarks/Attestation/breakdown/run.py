#!/usr/bin/env python3

import sys
import os
from pathlib import Path
from multiprocessing import Process, Value
import ctypes

lib = ctypes.CDLL("../../../module/libwallet/libwallet.so")
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet.restype = ctypes.c_char_p
lib.create_channel.argtypes = (ctypes.c_int, ctypes.c_int)

lib.monitor_connect()

with open("func.py","rb") as f:
    func = f.read()

def create_zygote():
    zygote = lib.create_zygote(b"../../../module/libpal-none.so",
                           b"manifest",
                           b"../../../module/libsysdb-none.so")
    return zygote

function_input = b"a" * 4096

def single():
    zygote = create_zygote()
    print(f"Zygote: {zygote}")
    trustlet = lib.create_trustlet(zygote, func)
    print(f"Trustlet: {trustlet}")
    ret = lib.invoke_trustlet(trustlet, function_input, 4096)

single()

