## How to use external directory in Wallet
### Preparation
```
cd ./module/libwallet/externel/
gcc -o helloworld helloworld.c
```

### Manifeset
- Example  (excerpt)
```
[libos]
entrypoint = "/external/helloworld"

[fs]
root.type = "tmpfs"
mounts = [
  { type = "pseudo", path = "/lib", uri = "lib" },
  { path = "/external", uri = "file:/root/module/libwallet/external" },
]
```
- With this configuration, trustlet applications can open and read `/external/file`

### Use external lib
- Copy gramine lib into this external dir
```
cd ./module/libwallet/externel/
cp -r <path/to>gramine-svsm/python-libs/lib/x86_64-linux-gnu/gramine/runtime/glibc lib
```
- Change the manifest so that `LD_LIBRARY_PATH` points to the lib
```
[loader.env]
LD_LIBRARY_PATH = "/external/lib"
```

