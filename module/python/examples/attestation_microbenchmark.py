import wallet

import os
from pathlib import Path
from typing import TypeAlias, List, Tuple, Dict, Any

FileName: TypeAlias = str | os.PathLike

SCRIPTDIR = Path(os.path.dirname(os.path.realpath(__file__)))

fn_in_out_size = 64 # size of function input/output in bytes

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
            
            w.measure_monitor_cold()
            print("Measured monitor cold.")
            w.measure_monitor_hot()
            print("Measured monitor hot.")

            zy = w.create_zygote(zygote, manifest, libos)       
            print(f"Created zygote {zy.process_id}")
            zy.prepare_measure_zygote_cold()
            print(f"Finished the preparation of zygote {zy.process_id} cold")
            zy.measure_zygote_cold()
            print(f"Measured zygote {zy.process_id} cold")
            zy.measure_zygote_hot()
            print(f"Measured zygote {zy.process_id} hot")

            func = b"print(\"Hello World!!\")"
            tr = zy.create_trustlet(func)
            print(f"Created zygote {tr.process_id}")
            tr.prepare_measure_trustlet_cold()
            print(f"Finished the preparation of trustlet {tr.process_id} cold")
            tr.measure_trustlet_cold()
            print(f"Measured trustlet {tr.process_id} cold")
            tr.measure_trustlet_hot()
            print(f"Measured trustlet {tr.process_id} hot")

            fn_input = b"test data!"
            fn_output = b"test data out!"
            tr.measure_function(fn_input, len(fn_input), fn_output, len(fn_output))
            print("Measured function.")

            pass


if __name__ == "__main__":
    import fire

    fire.Fire(Runner)
