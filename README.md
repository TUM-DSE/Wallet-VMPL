# Schal: Secure layering framework for confidential VMs

## Prerequisite
- Schal requires AMD SEV-SNP VMPL

## Usage

Initial Setup:
```bash
make prepare_all
```

Run CVM:
```bash
make run_svsm
```

Connect via SSH:
```bash
make ssh
```

Build Kernel Module (within VM):
```bash
cd module
make vmpl.ko
```

To Test Trustlet execution: 
```bash
make trustlet_test
```