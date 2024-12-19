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
            report = w.attest_monitor()
            print("Monitor attestation report is generated successfully.")
            print(report)

            zy = w.create_zygote(zygote, manifest, libos)
            print(f"Created zygote {zy.process_id}")
            
            func = b"print(\"Hello World!!\")"
            tr = zy.create_trustlet(func)
            print(f"Created trustlet {tr.process_id}")

            input = b"test data!"
            ret = tr.invoke_trustlet(input)
            print(f"Invoked trustlet {tr.process_id}, ret = {ret}")
            report = tr.attest_execution(input, len(input), ret, len(ret))
            print(f"Function {tr.process_id} attestation report is generated successfully.")
            print(report)

            pass


if __name__ == "__main__":
    import fire

    fire.Fire(Runner)
