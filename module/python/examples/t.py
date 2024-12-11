import wallet

import os
from pathlib import Path
from typing import TypeAlias, List, Tuple, Dict, Any

FileName: TypeAlias = str | os.PathLike

SCRIPTDIR = Path(os.path.dirname(os.path.realpath(__file__)))


class Runner:
    def __init__(self):
        pass

    def run(
        self,
        zygote: FileName = f"{SCRIPTDIR}/../../libpal.so",
        manifest: FileName = f"{SCRIPTDIR}/../../manifest",
        libos: FileName = f"{SCRIPTDIR}/../../libsysdb.so",
    ):
        with wallet.Wallet() as w:
            zy = w.create_zygote(zygote, manifest, libos)
            print(f"Created zygote {zy.process_id}")
            tr = zy.create_trustlet("print(1+1)")
            print(f"Created trustlet {tr.process_id}")
            tr2 = zy.create_trustlet("print(1+2)")
            print(f"Created trustlet {tr.process_id}")
            ret = tr.invoke_trustlet("Test")
            print(f"Invoked trustlet {tr.process_id}, ret = {ret}")
            ret = tr2.invoke_trustlet("Test2")
            print(f"Invoked trustlet {tr2.process_id}, ret = {ret}")
            pass


if __name__ == "__main__":
    import fire

    fire.Fire(Runner)
