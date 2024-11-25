# Wallet: Secure layering framework for confidential VMs

## Prerequisite
- Wallet requires AMD SEV-SNP VMPL
- This repository uses a Nix flake

## Usage

Initial Setup:
```bash
make prepare_all
```
This will do the following
- Clone all required submodules including the Monitor and Gramine
- Fetch the prebuild kernel, and VM base image
- Build the Monitor and Guest image
- Setup the network for the VMPL

``` bash
make gramine
```
This will build gramine and make it accessable to the VM.

Run CVM with Wallet:
```bash
make run
```
Starts the CVM with the Wallet Monitor.

Connect via SSH:
```bash
make ssh
```

Build Kernel Module (within VM):
```bash
cd module
make vmpl.ko
```

To Test Trustlet execution (within the VM): 
```bash
cd module
make
insmod vmpl.ko
make t
./test
```
