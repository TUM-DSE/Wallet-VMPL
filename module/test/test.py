import sys
#sys.path.append("../python")
import ctypes
import pickle
import wallet
import time

with open("../../Benchmarks/SeBS/benchmarks-data/400.inference/411.image-recognition/fake-resnet/800px-Porsche_991_silver_IAA.jpg","rb") as f:
    image = f.read()

with open("../../Benchmarks/SeBS/benchmarks-data/400.inference/411.image-recognition/model/resnet50-0676ba61.pth", "rb") as f:
    model = f.read()

input_dict = {"model": model, "image": image}
input_data = pickle.dumps(input_dict)

del input_dict["model"]
input_data2 = pickle.dumps(input_dict)

with open("function.py", "rb") as f:
    func = f.read()

with wallet.Wallet() as w:
    output_size = 200
    
    start = time.time_ns()
    zygote = w.create_zygote("../libpal-image-recognition.so", "python.manifest.template", "../libsysdb-image-recognition.so")
    end = time.time_ns()
    print(f"Zygote Creation Time {(end - start) / 1e9}")

    start = time.time_ns()
    trustlet_1 = zygote.create_trustlet("./function.py")
    end = time.time_ns()
    print(f"Trustlet Creation Time {(end - start) / 1e9}")

    print("Executing first Trustlet")

    run_1 = trustlet_1.invoke_trustlet_bin("",0)
    
    start = time.time_ns()
    run_1 = trustlet_1.invoke_trustlet_bin(input_data,0)
    end = time.time_ns()
    run_1 = trustlet_1.invoke_trustlet_bin("", output_size)
    
    out = pickle.loads(run_1)
    print(f"Execution Time: {(end - start) / 1e9}")
    print(out)

    #trustlet_2 = zygote.create_trustlet("./function.py")
    run_2 = trustlet_1.invoke_trustlet_bin("",0)
    start = time.time_ns()
    run_2 = trustlet_1.invoke_trustlet_bin(input_data2, 0)
    end = time.time_ns()
    run_2 = trustlet_1.invoke_trustlet_bin("",output_size)
    
    print(f"Execution Time: {(end - start) / 1e9}")
    out = pickle.loads(run_2)

    print(out)
