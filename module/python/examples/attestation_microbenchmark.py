import wallet

import os
import csv
import random
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

FileName: TypeAlias = str | os.PathLike

SCRIPTDIR = Path(os.path.dirname(os.path.realpath(__file__)))

fn_in_out_sizes = [64, 1024, 4096]  # size of function input/output in bytes
repeats = 20

class Runner:
    def __init__(self):
        pass

    @staticmethod
    def time_function(func):
        start = time.perf_counter_ns()
        func()
        end = time.perf_counter_ns()
        return end - start

    def save_results_to_csv(self, results):
        # Create a unique file name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = SCRIPTDIR / f"report_generation_measurements_{timestamp}.csv"

        # Prepare data for CSV
        with open(output_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Measurement", "Size (bytes)", "Average (ns)", "Median (ns)", "StdDev (ns)"])

            # Write monitor measurements
            for key in results.keys():
                if key != "measure_function":
                    avg = statistics.mean(results[key])
                    med = statistics.median(results[key])
                    stddev = statistics.stdev(results[key]) if len(results[key]) > 1 else 0.0
                    writer.writerow([key, "-", avg, med, stddev])
                else:
                    # Write function measurements
                    for size, values in results[key].items():
                        avg = statistics.mean(values)
                        med = statistics.median(values)
                        stddev = statistics.stdev(values) if len(values) > 1 else 0.0
                        writer.writerow([key, size, avg, med, stddev])

        print(f"Results saved to {output_file}")

    def run(
        self,
        zygote: FileName = f"{SCRIPTDIR}/../../libpal.so",
        manifest: FileName = f"{SCRIPTDIR}/../../manifest",
        libos: FileName = f"{SCRIPTDIR}/../../libsysdb.so",
    ):
        results = {  # To store measurements
            "measure_monitor_cold": [],
            "measure_monitor_hot": [],
            "measure_zygote_cold": [],
            "measure_zygote_hot": [],
            "measure_trustlet_cold": [],
            "measure_trustlet_hot": [],
            "measure_function": {size: [] for size in fn_in_out_sizes},
        }

        for _ in range(repeats):
            with wallet.Wallet() as w:
                w.attest_monitor()

                # Monitor measurements
                results["measure_monitor_cold"].append(self.time_function(w.measure_monitor_cold))
                results["measure_monitor_hot"].append(self.time_function(w.measure_monitor_hot))

                # Create zygote and measure
                zy = w.create_zygote(zygote, manifest, libos)
                zy.prepare_measure_zygote_cold()
                results["measure_zygote_cold"].append(self.time_function(zy.measure_zygote_cold))
                results["measure_zygote_hot"].append(self.time_function(zy.measure_zygote_hot))

                # Create trustlet and measure
                func = "func.py"
                tr = zy.create_trustlet(func)
                tr.prepare_measure_trustlet_cold()
                results["measure_trustlet_cold"].append(self.time_function(tr.measure_trustlet_cold))
                results["measure_trustlet_hot"].append(self.time_function(tr.measure_trustlet_hot))

                # Function measurements for different input/output sizes
                for size in fn_in_out_sizes:
                    fn_input = os.urandom(size)
                    fn_output = os.urandom(size)
                    results["measure_function"][size].append(
                        self.time_function(
                            lambda: tr.measure_function(fn_input, len(fn_input), fn_output, len(fn_output))
                        )
                    )

        # Calculate stats and save to CSV
        self.save_results_to_csv(results)
        pass

if __name__ == "__main__":
    import fire
    fire.Fire(Runner)
