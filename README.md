# Schal: Secure layering framework for confidential VMs

## Prerequisite
- Schal requires AMD SEV-SNP VMPL
- git-lfs is required for this repository


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
make 
make test
```
