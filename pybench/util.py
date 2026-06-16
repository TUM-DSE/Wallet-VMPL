from subprocess import check_output, STDOUT
from typing import cast, Any, TypeVar, Iterator, cast, List, Dict, Callable, Tuple, Any
import random
import string
from root import PROJECT_ROOT

def run(command: str) -> str:
    return check_output(command, stderr=STDOUT, shell=True).decode('utf-8')


T = TypeVar("T")

def safe_cast(typ: type[T], o: Any) -> T:
    """
    Bandaid around typing.cast: Shall be used to assert to static checkers that typing is correct. We therefore always cast, but at runtime we check if this cast is valid.
    """
    if type(o) != typ:
        raise TypeError(f"Cannot cast object to {typ}, because it is {type(o)}: {o}")

    return cast(typ, o)


A = TypeVar("A")

def deduplicate(l: List[A]) -> List[A]:
    """
    deduplicate based on equality while maintaining order
    """
    # return list(dict.fromkeys(l)) # this only works on __hash__()ables (so not on dataclasses)
    ret = []
    for i in l:
        if i not in ret:
            ret += [ i ]
    return ret


def product_dict(input_dict: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    current = dict()
    ret = _product_dict(input_dict, current)
    assert ret is not None
    return ret


def _product_dict(input_dict: Dict[str, List[Any]], current: Dict[str, Any], result=None, keys: List[str] | None = None, index=0) -> List[Dict[str, Any]] | None:
    """
    Generates all combinations of lists contained in a dictionary, where each combination is represented as a dictionary with the same keys.
    Note, that current must not be initialized in the function definition  with a default value. Otherwise the pointer to the same dict will be reused across function invocations.
    """
    # Initialize result list and keys on the first call
    if result is None:
        result = []
        keys = list(input_dict.keys())  # Extract keys to maintain order
    assert keys is not None

    # Base case: If current combination is complete, add it to the result
    if index == len(keys):
        result.append(current.copy())  # Use copy to avoid reference issues
        return

    # Recursive case: Iterate through the current list and recurse for the next list
    current_key = keys[index]
    for item in input_dict[current_key]:
        current[current_key] = item  # Assign current item to its key in the current combination
        _product_dict(input_dict, result=result, keys=keys, index=index + 1, current=current)

    return result


def strip_subnet_mask(ip_addr: str):
    return ip_addr[ : ip_addr.index("/")]

def randomword(length):
   letters = string.ascii_lowercase
   return ''.join(random.choice(letters) for i in range(length))

def _kvm_loaded_build_id(server) -> str:
    # /sys/module/kvm/notes/.note.gnu.build-id is the raw ELF note
    # (header + "GNU\0" + 20-byte SHA1). The last 40 hex chars are the id.
    return server.exec(
        "od -An -tx1 /sys/module/kvm/notes/.note.gnu.build-id "
        "| tr -d ' \\n' | tail -c 40"
    ).strip()


def _kvm_file_build_id(server, path: str) -> str:
    if path.endswith(".xz"):
        # readelf can't seek a pipe, so stage to a temp file.
        cmd = (
            f"TMP=$(mktemp --suffix=.ko) && "
            f"xzcat {path} > $TMP && "
            f"readelf -n $TMP | awk '/Build ID:/ {{print $3; exit}}'; "
            f"rm -f $TMP"
        )
    else:
        cmd = f"readelf -n {path} | awk '/Build ID:/ {{print $3; exit}}'"
    return server.exec(cmd).strip()


def is_kvm_version(server, of_system=False, of_wallet=False) -> bool:
    """
    Check which kvm.ko is currently loaded by comparing GNU build-ids
    (linker-stamped, unique per build).

    Symbol-name probes don't work here: the NixOS stock kernel already
    carries the SVSM/VMPL symbols, so symbol presence can't distinguish
    it from host/kvm/kvm.ko. coresize is also unreliable (loader padding,
    per-cpu replication, kallsyms retention all inflate it).

    of_system: stock kvm in /run/booted-system/kernel-modules/...
    of_wallet: project kvm at host/kvm/kvm.ko
    """
    assert of_system ^ of_wallet, "Exactly one of of_system / of_wallet must be set"

    if of_system:
        kernel = server.exec("uname -r").strip()
        path = f"/run/booted-system/kernel-modules/lib/modules/{kernel}/kernel/arch/x86/kvm/kvm.ko.xz"
    else:
        path = f"{PROJECT_ROOT}/host/kvm/kvm.ko"

    return _kvm_loaded_build_id(server) == _kvm_file_build_id(server, path)


