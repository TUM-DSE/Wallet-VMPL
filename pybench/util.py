from subprocess import check_output, STDOUT
from typing import cast, Any, TypeVar, Iterator, cast, List, Dict, Callable, Tuple, Any
import random
import string

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
