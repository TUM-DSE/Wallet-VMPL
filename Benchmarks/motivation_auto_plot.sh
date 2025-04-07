#!/usr/bin/env bash

# automate the motivation plotting

cd Attestation
python3 plot.py results.csv
cd ..

cd Boottime
python3 plot.py results.txt
cd ..

cd Communication_cost
python3 plot.py results.txt
cd ..

cd scale
python3 plot.py results.csv
cd ..

cd Simulation_analysis
python3 plot_simulation_CDF.py results/wallet500_sw_dyn_small_nodes.txt
cd ..