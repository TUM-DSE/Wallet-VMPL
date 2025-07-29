import ctypes
lib = ctypes.CDLL("./libwallet.so")
lib.monitor_connect()
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet.restype = ctypes.c_char_p
lib.create_channel.argtypes = (ctypes.c_int, ctypes.c_int)

zid1 = lib.create_zygote(b"../libpal.so", b"manifest", b"../libsysdb.so")
func = b""
tid1 = lib.create_trustlet(zid1, func)

input_data = b"input data"
output_size = 4096
output1 = lib.invoke_trustlet(tid1, input_data, output_size)

#output2 = lib.invoke_trustlet(tid2, input_data, output_size)

# expected output:
# output tid2: output from id=2: input='output from id=1: input='input data''
