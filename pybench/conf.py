from configparser import ExtendedInterpolation
import getpass
from os.path import abspath, realpath, dirname, basename
from configparser import ConfigParser, ExtendedInterpolation
from dataclasses import dataclass

FILEDIR: str = abspath(dirname(realpath(__file__)))
PDIR: str = dirname(dirname(FILEDIR)) # this file is expected to be at ./*/*/autotest.py relative to project root
PDIR_PARENT: str = dirname(PDIR)
PDIR_NAME: str = basename(PDIR)
USERNAME: str = getpass.getuser()
CONFIG_DEFAULTS = {
        "projectDirectory": PDIR,
        "projectDirectoryName": PDIR_NAME,
        "projectDirectoryParent": PDIR_PARENT,
        "username": USERNAME
       }

def default_config_parser() -> ConfigParser:
    return ConfigParser(defaults=CONFIG_DEFAULTS, interpolation=ExtendedInterpolation())

@dataclass
class Globals:
    """
    Mutable globals need to be wrapped in a heap object.
    Otherwise modification don't propagate to other modules because they still have the old pointer.
    Take care to initialize the values before use!
    """
    OUT_DIR = "/tmp/uninitialized"
    BRIEF = False
    DURATION_S = 0

G: Globals = Globals()
