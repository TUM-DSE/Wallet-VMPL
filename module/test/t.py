import sys
sys.path.append("../python")
import ctypes
import pickle
import wallet

with open("800px-Porsche_991_silver_IAA.jpg","rb") as f:
    image = f.read()

with open("resnet50-0676ba61.pth", "rb") as f:
    model = f.read()

input_data = {"model": model, "image": image}
input_data = pickle.dumps(input_data)
with open("function.py", "rb") as f:
    func = f.read()

with wallet.Wallet() as w:
    output_size = 200
    
    zygote = w.create_zygote("../libpal-image-recognition.so", "python.manifest.template", "../libsysdb-image-recognition.so")
    trustlet_1 = zygote.create_trustlet("./function.py")
    
    print("Executing first Trustlet")

    run_1 = trustlet_1.invoke_trustlet_bin("",0)
    run_1 = trustlet_1.invoke_trustlet_bin(input_data,0)
    run_1 = trustlet_1.invoke_trustlet_bin("", output_size)
    
    out = pickle.loads(run_1)
    print(out)

    trustlet_2 = zygote.create_trustlet("./function.py")

    run_2 = trustlet_1.invoke_trustlet_bin("",0)
    run_2 = trustlet_2.invoke_trustlet_bin(input_data, 0)
    run_2 = trustlet_2.invoke_trustlet_bin("",output_size)
    
    out = pickle.loads(run_2)

    print(out)
