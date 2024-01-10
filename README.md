# Schal: Secure layering framework for confidential VMs

## Usage
Initial Setup:
```bash
make prepare_all
```

Run CVM:
```bash
sudo make run_svsm
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
