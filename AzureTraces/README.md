follow https://github.com/dimstav23/invitro/blob/1ef2280f8c3f98112798778d8017a2d2fb2e48b5/README.md#wallet-notes to download and preprocess the data

## Preprocess the trace

Skip this step. It is obsolete.

If you want to run a freshly downloaded trace, it needs to be preprocessed in order to include the start timestamp which is calculated from the end timestamp and the duration.

```
python preprocess.py <input_file> <output_file>
```

## Running the simulation

```
python sim_node_scalability.py <input_file>
```

where <input_file> is a durations.csv (e.g. ../invitro/data/traces/azure_wallet/sampled_500/samples/500/durations.csv).

The parameters for the simulation can be configured inside this script prior to running it. 

The scirpt generates a result file called  `simulation_results_parallel.txt` which contains all the results from the simulation.

## Plotting the results

The plotting script can be found on the `dimstav23/update_plots` branch at `Benchmarks/Simulation_analysis/plot_simulation_CDF.py`.

The results file generated in the previous step can the be given to the script. The plots will be saved to a newly generated `output` directory.


# Slick simulation:

```
cd AzureTraces
python3 simulate.py -total_cores 2048 -cold_start 3.5 -reschedule 0.000016 -concurrent_per_vnf 512 -input_file invitro/wallet_traces/wallet_traces_4000/function_invocations.csv
python3 sim_node_scalability.py invitro/wallet_traces/wallet_traces_4000/function_invocations.csv

cd ../Benchmarks/Simulation_analysis
python3 plot_simulation_CDF.py ../../AzureTraces/simulation_results_parallel.txt
```
