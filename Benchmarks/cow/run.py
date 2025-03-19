import ctypes
import sys
import time
lib = ctypes.CDLL("../../module/libwallet/libwallet.so")
print(lib.monitor_connect())
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet.restype = ctypes.c_char_p
lib.create_channel.argtypes = (ctypes.c_int, ctypes.c_int)

zid1 = lib.create_zygote(b"libpal.so", b"manifest", b"libsysdb.so")
func = b""
tid1 = lib.create_trustlet(zid1, func)
tid2 = lib.create_trustlet(zid1, func)
time.sleep(5)
input_data = b"a"
output_size = 1
print("First")
output1 = lib.invoke_trustlet(tid1, input_data, output_size)
#time.sleep(5)
print("Second")
output1 = lib.invoke_trustlet(tid2, input_data, output_size)
