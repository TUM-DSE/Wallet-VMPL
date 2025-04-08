import ctypes
import pickle
lib = ctypes.CDLL("../../libwallet/libwallet.so")
lib.monitor_connect()
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet.restype = ctypes.c_char_p
lib.invoke_trustlet_bin.restype = ctypes.c_void_p
lib.create_channel.argtypes = (ctypes.c_int, ctypes.c_int)

input_data = {"random_len": 1000}
input_data = pickle.dumps(input_data)
print(len(input_data))
with open("function.py", "rb") as f:
    func = f.read()

zid1 = lib.create_zygote(b"../../libpal-html.so", b"python.manifest.template", b"../../libsysdb-html.so")

tid1 = lib.create_trustlet(zid1, func)

#input_data = b"input data"
print("INVOKE",flush = True)
output_size = 36000
output1 = lib.invoke_trustlet_bin(tid1, "", 0, 0)
print(output1)
import pdb
print("INVOKE 2", flush = True)
output2 = lib.invoke_trustlet_bin(tid1, input_data,len(input_data), 0)
print(output2, flush=True)
print("INVOKE 3", flush = True)
output3 = lib.invoke_trustlet_bin(tid1, "",0, output_size)
print(output3)
#output3 = lib.invoke_trustlet_bin(tid1, "",len(""), output_size)
#print(output3)
print(hex(output3))
#breakpoint()
out = (ctypes.c_byte * output_size).from_address(output3)
print("Test", flush=True)
#print("Test: ", out.value, flush=True)
out = pickle.loads(out)

#out = pickle.loads(output2)
print(out)
# expected output:
# output tid2: output from id=2: input='output from id=1: input='input data''
