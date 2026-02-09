# Wallet

## The daily init

Remembe to run `make setup_guest_net && make unload_kvm && make load_kvm` after every host reboot.


## Debug and verbose builds

SVSM:

When turning on the `print` build feature, debug verbosity is turned on (log level set in `svsm/kernel/Cargo.toml` between `error, warn, info, debug, trace`).
Turn on `print` with `make build_svsm LOG_LEVEL=print` or permanently in the Makefile.

Trustlet:

For trustlet prints to appear, SVSM must be built with debug verbosity, _and_ the manifest must set the `[loader]`'s to `loglevel = "debug"`.
When the trustlet prints (needs explicit flush for stdout), SVSM will print it with `info` level.


## Trustlet File System

The file system is generated via scripts in `runtime/filesystem/*/` and then compiled into gramine.
With, e.g., `make simple_fs` you copy files into place and compile it into a file system.
With `make gramine` you then add the new file system into the gramine image. Perhaps you also need to rebuild `make build_svsm`.
