
### Getting Started

The first step is to get the source code for Wallet and enter the nix shell
```bash
git clone https://github.com/TUM-DSE/Wallet-VMPL.git --branch slick-dev
cd Wallet-VMPL
nix develop
```
In order to get everthing ready the next step is to run the
initialization.
```bash
make initialize
make simple_slick_fs
make gramine
make build_svsm
```
This step will fetch and build the dependecies to run a simple Trustlet.
In the next step we run the VM with Wallet's Monitor.
```bash
make run
```
After the VM has started it can be accessed either via ssh (`make ssh`) or
by login in with `root:root`. Since the Montior also logs to the same output
ssh is recommended.

In the VM the `module` directory should be available.
```bash
make vmpl.ko
insmod vmpl.ko
```
This will load the kernel module used to commuicate with the Monitor.

In the next step the user space library can be build.
```bash
make -C libwallet/ libwallet.so
make -C libwallet/ libwallet.a
```
And in `module/python` the python library can be build.
```bash
python3 -m pip install pybind11 pytest fire
python3 setup.py install
```

At this point the preperation are completed and the runtime can be tested.
With the script at `module/example-slick` a simple Trustlet can be created
and excecuted.
```bash
python3 ipc_run.py
# or
make run
./run
```
This will exectue `module/example-slick/com.c` in VMPL2 as a Trustlet.
