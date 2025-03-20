#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import pprint as pprint

# Common graph settings
mpl.use("Agg")
mpl.rcParams["font.family"] = "libertine"
sns.set_style("whitegrid")
sns.set_style("ticks", {"xtick.major.size": 8, "ytick.major.size": 8})
sns.set_context("paper", rc={"font.size": 5, "axes.titlesize": 5, "axes.labelsize": 8})

TITLE_FONTSIZE = 7
TICKS_FONTSIZE = 5
LEGEND_FONTSIZE = 5
ANNOTATION_SIZE = 4
figwidth = 4.3  # 3.3 inch for single column, 7 inch for double column
figheight = 2.2
VARIANTS = ['native', 'gramine', 'kata', 'vm', 'cvm', 'wallet_cow_prealloc', 'wallet_cow_no_prealloc']
LABEL_MAPPINGS = {
    'native'  : 'Native',
    'gramine' : 'LibOS (Gramine)',
    'kata'    : 'Containers (Kata)',
    'vm'      : 'VM (KVM-Linux)',
    'cvm'     : 'CVM (SEV-SNP)',
    'wallet_cow_prealloc'  : 'Wallet',
    'wallet_cow_no_prealloc' : 'Wallet',
}

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer', 
    '311.compression',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    '504.dna-visualisation'
]
palette = sns.color_palette("pastel", n_colors=len(VARIANTS))
hatches = ["", "//", "xx", "\\\\", ".."]
linestyles = ["-", "--", "-.", ":", "-"]

def load_and_process_data():
    """Load and process data from all variants and benchmarks"""
    data = []
    
    # Find common benchmarks across all variants
    common_benchmarks = set()
    first = True
    for variant in VARIANTS:
        variant_path = Path(f"./results/{variant}")
        if not variant_path.exists():
            print(f"Variant path {variant_path} not found")
            exit()
            
        current_benchmarks = set()
        for bench in BENCHMARKS:
            result_path = variant_path / bench / "perf-cost" / "result.csv"
            if result_path.exists():
                current_benchmarks.add(bench)
        
        # Preserve only the benchmarks that all the variants have in common
        if first:
            common_benchmarks = current_benchmarks
            first = False
        else:
            common_benchmarks &= current_benchmarks

    # Load data for common benchmarks
    for variant in VARIANTS:
        print(variant)
        for bench in common_benchmarks:
            result_path = Path(f"./results/{variant}/{bench}/perf-cost/result.csv")
            if result_path.exists():
                df = pd.read_csv(result_path)
                #print(df, result_path)
                # Calculate averages for cold and hot runs for specific columns only
                cold_mask = df['type'] == 'cold'
                hot_mask = df['type'] == 'sequential'

                
                cold_exec = df[cold_mask]['exec_time'].mean() / 1000 / 1000  # Convert μs to ms
                cold_client = df[cold_mask]['client_time'].mean() / 1000 / 1000  # Convert μs to ms
                hot_exec = df[hot_mask]['exec_time'].mean() / 1000 / 1000  # Convert μs to ms
                hot_client = df[hot_mask]['client_time'].mean() / 1000 / 1000  # Convert μs to ms
                
                # Add both cold and hot data
                data.append({
                    'variant': variant,
                    'benchmark': bench,
                    'type': 'cold',
                    'exec_time': cold_exec,
                    'client_time': cold_client
                })
                data.append({
                    'variant': variant,
                    'benchmark': bench,
                    'type': 'hot',
                    'exec_time': hot_exec,
                    'client_time': hot_client
                })
            else:
                print(f"Result path {result_path} not found")
                exit()
    
    return pd.DataFrame(data), list(common_benchmarks)

def create_wallet_combined_plot(df, benchmarks, metric, output_dir, y_scale='linear'):
    """Create grouped bar chart with all four wallet variants in a single plot"""
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Prepare data for the four combinations
    cold_no_prealloc = df[(df['type'] == 'cold') & (df['variant'] == 'wallet_cow_no_prealloc')]
    cold_prealloc = df[(df['type'] == 'cold') & (df['variant'] == 'wallet_cow_prealloc')]
    hot_no_prealloc = df[(df['type'] == 'hot') & (df['variant'] == 'wallet_cow_no_prealloc')]
    hot_prealloc = df[(df['type'] == 'hot') & (df['variant'] == 'wallet_cow_prealloc')]
    
    # Calculate geometric means for each variant+type combination
    geomean_cold_no_prealloc = np.exp(np.mean(np.log(cold_no_prealloc[metric].values))) if len(cold_no_prealloc) > 0 and np.all(cold_no_prealloc[metric].values > 0) else np.nan
    geomean_cold_prealloc = np.exp(np.mean(np.log(cold_prealloc[metric].values))) if len(cold_prealloc) > 0 and np.all(cold_prealloc[metric].values > 0) else np.nan
    geomean_hot_no_prealloc = np.exp(np.mean(np.log(hot_no_prealloc[metric].values))) if len(hot_no_prealloc) > 0 and np.all(hot_no_prealloc[metric].values > 0) else np.nan
    geomean_hot_prealloc = np.exp(np.mean(np.log(hot_prealloc[metric].values))) if len(hot_prealloc) > 0 and np.all(hot_prealloc[metric].values > 0) else np.nan
    
    # Add geomean data to display
    all_benchmarks = benchmarks + ['geomean']
    
    # Calculate bar positions
    width = 0.15  # Width of each bar
    positions = np.arange(len(all_benchmarks))
    
    # Define colors and hatches
    cold_color = palette[0]  # First color for cold
    hot_color = palette[1]   # Third color for hot
    no_hatch = ""           # No hatch for no_prealloc
    yes_hatch = "/"        # Hatch for prealloc
    
    # Plot bars for each combination
    # Cold no prealloc
    cold_no_prealloc_values = list(cold_no_prealloc[metric].values)
    cold_no_prealloc_values.append(geomean_cold_no_prealloc)
    positions_cold_no = positions - width*1.5
    bars1 = ax.bar(positions_cold_no, cold_no_prealloc_values, width, 
                 label='Cold start (w/o preallocation)',
                 color=cold_color, edgecolor='black', hatch=no_hatch)
    
    # Cold with prealloc
    cold_prealloc_values = list(cold_prealloc[metric].values)
    cold_prealloc_values.append(geomean_cold_prealloc)
    positions_cold_yes = positions - width*0.5
    bars2 = ax.bar(positions_cold_yes, cold_prealloc_values, width, 
                 label='Cold start (w/ preallocation)',
                 color=cold_color, edgecolor='black', hatch=yes_hatch)
    
    # Hot no prealloc
    hot_no_prealloc_values = list(hot_no_prealloc[metric].values)
    hot_no_prealloc_values.append(geomean_hot_no_prealloc)
    positions_hot_no = positions + width*0.5
    bars3 = ax.bar(positions_hot_no, hot_no_prealloc_values, width, 
                 label='Hot start (w/o preallocation)',
                 color=hot_color, edgecolor='black', hatch=no_hatch)
    
    # Hot with prealloc
    hot_prealloc_values = list(hot_prealloc[metric].values)
    hot_prealloc_values.append(geomean_hot_prealloc)
    positions_hot_yes = positions + width*1.5
    bars4 = ax.bar(positions_hot_yes, hot_prealloc_values, width, 
                 label='Hot start (w/ preallocation)',
                 color=hot_color, edgecolor='black', hatch=yes_hatch)
    
    # Customize the plot
    ax.set_yscale(y_scale)
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    ax.set_xticks(positions)
    xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
    ax.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
    
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    legend = plt.legend(bbox_to_anchor=(0.01, 0.98), loc='upper left',
                      borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    
    # Add gridlines
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    if(y_scale != "log"):
        ax.set_ylim(bottom=0)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'wallet_prealloc_{metric}_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'wallet_prealloc_{metric}_{y_scale}.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def main():
    global VARIANTS
    # Load and process the wallet cow variants only
    VARIANTS = ['wallet_cow_prealloc', 'wallet_cow_no_prealloc']
    df, common_benchmarks = load_and_process_data()
    
    # Create separate plots for each metric and execution type
    metrics = ['exec_time', 'client_time']
    # Create new combined plots with all four wallet variants
    for metric in metrics:
        create_wallet_combined_plot(df, common_benchmarks, metric, 'output', 'linear')
        create_wallet_combined_plot(df, common_benchmarks, metric, 'output', 'log')
    
    print("Plots saved in output directory")

if __name__ == "__main__":
    main()
