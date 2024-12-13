# Available at setup time due to pyproject.toml
from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

__version__ = "0.0.1"

# The main interface is through Pybind11Extension.
# * You can add cxx_std=11/14/17, and then build_ext can be removed.
# * You can set include_pybind11=false to add the include directory yourself,
#   say from a submodule.
#
# Note:
#   Sort input source files if you glob sources to ensure bit-for-bit
#   reproducible builds (https://github.com/pybind/python_example/pull/53)

ext = Pybind11Extension(
        "_wallet",
        ["src_ext/main.cpp"],
        define_macros=[("VERSION_INFO", __version__)],
        )
ext._add_ldflags(["-L../libwallet", "-l:libwallet.a"])
ext._add_cflags(["-I../libwallet/src/", "-L../libwallet" ,"-l:libwallet.a"])
ext_modules = [
    ext,
        ]


setup(
    name="wallet",
    version=__version__,
    url="https://github.com/TUM-DSE/Wallet-VMPL",
    description="A python interface for the Wallet",
    long_description="",
    packages=["wallet"],
    ext_modules=ext_modules,
    extras_require={"test": "pytest"},
    test_suite="tests",
    # Currently, build_ext only provides an optional "highest supported C++
    # level" feature, but in the future it may provide more features.
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
    python_requires=">=3.7",
)
