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
            zid = w.create_zygote(zygote, manifest, libos)
            print(f"Created zygote {zid}")
            tid = w.create_trustlet(zid)
            print(f"Created trustlet {tid}")
            ret = w.invoke_trustlet(tid)
            print(f"Invoked trustlet {tid}, ret = {ret}")


if __name__ == "__main__":
    import fire

    fire.Fire(Runner)
