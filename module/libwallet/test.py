import time
import ctypes
import json
import base64

benchmark = 504
path = "../../Benchmarks/SeBS/benchmarks/"
func = b""
data = b""

if benchmark == 501:
    path += "500.scientific/501.graph-pagerank/python/function.py"
    data = b"{\"size\": 10}"
elif benchmark == 502:
    path += "500.scientific/502.graph-mst/python/function.py"
    data = b"{\"size\": 10}"
elif benchmark == 503:
    path += "500.scientific/503.graph-bfs/python/function.py"
    data = b"{\"size\": 10}"
elif benchmark == 504:
    path += "500.scientific/504.dna-visualisation/python/function.py"
    tmp = {}

    bench_data_path = "../../Benchmarks/SeBS/benchmarks-data/500.scientific/504.dna-visualisation/bacillus_subtilis.fasta"
    with open(bench_data_path, "rb") as f:
        bench_data = f.read()
    tmp['data'] = base64.b64encode(bench_data).decode('utf-8')
    data = json.dumps(tmp).encode('utf-8') + b'\x00'

with open(path, "rb") as f:
    func = f.read()

print(func)

lib = ctypes.CDLL("./libwallet.so")
lib.monitor_connect()
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
zid = lib.create_zygote(b"../libpal.so",b"manifest",b"../libsysdb.so")
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)

tid1 = lib.create_trustlet(zid, func)
#tid2= lib.create_trustlet(zid, func)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet.restype = ctypes.c_char_p


res = lib.invoke_trustlet(tid1,data,0)
print(res)
#res2 = lib.invoke_trustlet(tid1,b"{}",0)
#print(res2)
#lib.invoke_trustlet(tid2,b"test data!",0)
