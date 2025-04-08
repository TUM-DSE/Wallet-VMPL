import ctypes
import pickle
lib = ctypes.CDLL("../libwallet/libwallet.so")
lib.monitor_connect()
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet.restype = ctypes.c_char_p
lib.create_channel.argtypes = (ctypes.c_int, ctypes.c_int)

with open("800px-Porsche_991_silver_IAA.jpg","rb") as f:
    image = f.read()

with open("resnet50-0676ba61.pth", "rb") as f:
    model = f.read()

input_data = {"model": model, "image": image}
input_data = pickle.dumps(input_data)
print(len(input_data))
with open("function.py", "rb") as f:
    func = f.read()

zid1 = lib.create_zygote(b"../libpal-image-recognition.so", b"python.manifest.template", b"../libsysdb-image-recognition.so")

tid1 = lib.create_trustlet(zid1, func)

#input_data = b"input data"
print("INVOKE",flush = True)
output_size = 4096
print(len(input_data))
output1 = lib.invoke_trustlet_bin(tid1, input_data, len(input_data), output_size)
import pdb
print("INVOKE 2", flush = True)
output2 = lib.invoke_trustlet_bin(tid1, "",len(""), output_size)
print(output2, flush=True)
breakpoint()
out = (ctypes.c_char * 1).from_address(output2)
print("Test", flush=True)
print("Test: ", out.value, flush=True)
out = pickle.loads(out)

#out = pickle.loads(output2)
print(out)
# expected output:
# output tid2: output from id=2: input='output from id=1: input='input data''
