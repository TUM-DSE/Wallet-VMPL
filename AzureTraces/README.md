## Preprocess the trace

If you want to run a freshly downloaded trace, it needs to be preprocessed in order to include the start timestamp which is calculated from the end timestamp and the duration.

```
python preprocess.py <input_file> <output_file>
```

## Running the simulation

```
python sim_node_scalability.py <input_file>
```

The parameters for the simulation can be configured inside this script prior to running it. 

The scirpt generates a result file called  `simulation_results_parallel.txt` which contains all the results from the simulation.

## Plotting the results

The plotting script can be found on the `dimstav23/update_plots` branch at `Benchmarks/Simulation_analysis/plot_simulation_CDF.py`.

The results file generated in the previous step can the be given to the script. The plots will be saved to a newly generated `output` directory.
