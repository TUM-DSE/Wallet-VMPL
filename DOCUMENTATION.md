# Wallet

## The daily init

Remembe to run `make setup_guest_net` after every host reboot.


## Trustlet File System

The file system is generated via scripts in `runtime/filesystem/*/` and then compiled into gramine.
With, e.g., `make simple_fs` you copy files into place and compile it into a file system.
With `make gramine` you then add the new file system into the gramine image. Perhaps you also need to rebuild `make build_svsm`.
