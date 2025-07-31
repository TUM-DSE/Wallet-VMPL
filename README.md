# Wallet: Confidential Serverless Computing 

## For evaluation testers
Due to the special hardware requirments we provide ssh access to our evalution machines.
Please contact the paper author to obtain ssh access. The machines will have the correct hardware and kernel version to run the experiments. If you run into any problems you can write an email to the authors.

## Reproduction of paper results

### Prerequisite

#### Hardware

- AMD EPYC 7713P with AMD SEV-SNP support enabled

#### Software

- Linux kernel 6.8 with Wallet specific [patches](https://github.com/TUM-DSE/doctor-cluster-config/blob/bf91a4e6a5d07adb7f6bff07ea9d27db6973aa32/pkgs/kernels/linux-svsm-host-wallet.nix#L62)
- Nix for dependency management 

### Getting Started

The first step is to get teh source code for Wallet. 
```bash
git clone https://github.com/TUM-DSE/Wallet-VMPL.git
```
In order to get everthing ready the next step is to run the 
initialization.
```bash
make initialize
```
This step will fetch the required dependencies, build the
guest OS image, the Zygote images, KVM, and the Monitor.

In order to test if the Monitor is working the following can be run.
```bash
make run
```
This will start a VMPL capable CVM with the Monitor.
If the guest OS boots to the login prompt everything should work.

### Running experiments
At this point the steps in getting started should have build all required binaries used the experiments. 

#### 7.2 End-to-end Performance
Use the Makefile to run the experiments.
```bash
make run_sebs_wallet
make run_sebs_vm
make run_sebs_cvm
make run_sebs_kata
make run_sebs_gramine
make run_sebs_native
```
Each will run all SeBS benchmarks and provide the logs of all.
Figure 7 can be generated with the following command.
```bash
make plot_end_to_end
```

#### 7.3 Performance Analysis
The data produced by the benchmarks of the previous step can also be use 
to create Figure 8a.
```bash
make plot_invocation_latency
```

---

For Figure 8b additinal benchmarks are required.
```bash
make run_sebs_wallet_breakdown
```
This will run the SeBS benchmarks with the Monitor configured to
log each step of the function creation.
```bash
make plot_runtime_breakdown
```

---

For Figure 8c the benchmarks is required to log the CoW and non-CoW pages.
```bash
make run_sebs_wallet_memory
```
```bash
make plot_memory_usage
```

#### 7.5 Communication Analysis
This benchmark does test communication overhead for the different baselines.
```bash
make run_comm_latency_wallet
make run_comm_latency_kata
make run_comm_latency_vm
make run_comm_latency_cvm
```
With the following Figure 9 can be generated.
```bash
make plot_comm_latency     
```

#### 7.6 Scale-out Performance
For this part public [Azure traces](https://github.com/Azure/AzurePublicDataset) are used.
The extend traces should already be part of the data prepared in the [Getting Started](#getting-started) section.
How the traces were extended can be found under [here](https://github.com/dimstav23/invitro/tree/wallet_trace_generation?tab=readme-ov-file#wallet-notes).
The simulations can be run with the following command.
```bash
make run_simulation
```
And Figure 10 can be created via the following.
```bash
make plot_simulation
```

### Additinal experiments

#### 3. Motivation

The data for Figure 1a can be generated via the following commands.
```bash
make run_boottime_native
make run_boottime_kata
make run_boottime_gramine
make run_boottime_cvm
make run_boottime_wallet
```
This will measure the boot time for each baseline including all 
parts of the wallet bootup, e.g. cold, lukewarm and warm.

```bash
make plot_boottime_motivation
```

---

For Figure 1b the following is required.
```bash
make run_comm_native
make run_comm_gramine
make run_comm_kata
make run_comm_vm
make run_comm_cvm
make run_comm_wallet
```
This will run the communication benchmark with increased transfer size
for each baseline.
```bash
make plot_comm_motivation
```

---

Information on how to generate Figure 1c can be found [here](https://github.com/TUM-DSE/CVM_eval/blob/wal-network-bench/experiment/bench_network_wal.sh#L3)

---


# Potential Issues

## KVM issues
It can happen that the KVM version of Wallet was not loaded. In this case please make sure to load it via `make load_kvm`. 

## Issues with regular SEV-SNP VMs
In the current version/kernel used for Wallet regular CVMs without a Monitor can't be run. 
In order to run all the benchmarks either the kernel needs to be changed or a second system is required.



