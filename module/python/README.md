# Wallet Python Interface

## Quick start
```
apt install python3 python3-pip
python3 -m pip install pybind11 pytest fire
python3 setup.py develop
python3 examples/t.py run
```

## Develop
```
python3 setup.py develop
# This compiles src_ext and builds _wallet.*.so
# python3
# >>> import wallet
```
- Edit [./src_ext](./src_ext) to change C++ code
- Edit [./wallet](./wallet) to change python code

## Test
```
pytest
```
- See [./tests](./tests)

## Install
```
python3 setup.py install
```
