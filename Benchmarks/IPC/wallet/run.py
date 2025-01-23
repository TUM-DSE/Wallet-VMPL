import ctypes
import sys
lib = ctypes.CDLL("../../../module/libwallet/libwallet.so")
lib.monitor_connect()
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet.restype = ctypes.c_char_p
lib.create_channel.argtypes = (ctypes.c_int, ctypes.c_int)

zid1 = lib.create_zygote(b"libpal.so", b"manifest_ipc_1", b"libsysdb.so")
func = b""
tid1 = lib.create_trustlet(zid1, func)

zid2 = lib.create_zygote(b"libpal.so", b"manifest_ipc_2", b"libsysdb.so")
tid2 = lib.create_trustlet(zid2, func)

lib.create_channel(tid1, tid2)

if len(sys.argv) > 1:
    output_size = int(sys.argv[1])
    iterations = int(sys.argv[2])
else:
    output_size = 64
    iterations = 5

input_data = b"a"
input_data = input_data * (output_size-1) +b"\00"
output1 = lib.invoke_trustlet(tid1, input_data, output_size)
output2 = lib.invoke_trustlet(tid2, b"", output_size)

print(f"Data size: {output_size}")
iter = 0
while iter < iterations:
    print(f"Iteration: {iter}")
    output1 = lib.invoke_trustlet(tid1, input_data, output_size)

    output2 = lib.invoke_trustlet(tid2, b"", output_size)
    print(f"output tid2: {output2.decode('utf-8')}")

    iter += 1




# expected output:
# output tid2: output from id=2: input='output from id=1: input='input data''
