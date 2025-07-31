import sys
#sys.path.append("../python")
import ctypes
import pickle
import wallet
import time

with open("function.py", "rb") as f:
    func = f.read()

def run_function(trustlet, data, outsize):
    run = trustlet.invoke_trustlet_bin("",0)
    run = trustlet.invoke_trustlet_bin(data,0)
    run = trustlet.invoke_trustlet_bin("", outsize)
    out = pickle.loads(run)
    print("Result: ", out)

with wallet.Wallet() as w:
    output_size = 200
    
    zygote = w.create_zygote("../libpal-none.so", "python.manifest.template", "../libsysdb-none.so")

    trustlet_1 = zygote.create_trustlet("./function.py")

    input_dict = {"Input": 5}
    input_data = pickle.dumps(input_dict)

    print("Executing Trustlet")

    run_function(trustlet_1, input_data, 50)
