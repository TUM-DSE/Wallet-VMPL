#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path

# Common graph settings
mpl.use("Agg")
mpl.rcParams["font.family"] = "libertine"
sns.set_style("whitegrid")
sns.set_style("ticks", {"xtick.major.size": 8, "ytick.major.size": 8})
sns.set_context("paper", rc={"font.size": 5, "axes.titlesize": 5, "axes.labelsize": 8})

TITLE_FONTSIZE = 8
TICKS_FONTSIZE = 7
LEGEND_FONTSIZE = 6
figwidth = 3.3  # 3.3 inch for single column, 7 inch for double column
figheight = 2.2
VARIANTS = ['gramine', 'native', 'vm', 'wallet']
BENCHMARKS = [
    '110.dynamic-html', '120.uploader', '210.thumbnailer', 
    '220.video-processing', '311.compression', '411.image-recognition',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs', 
    '504.dna-visualisation'
]
palette = sns.color_palette("pastel")
hatches = ["", "//", "xx", "\\\\", ".."]

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
        for bench in common_benchmarks:
            result_path = Path(f"./results/{variant}/{bench}/perf-cost/result.csv")
            if result_path.exists():
                df = pd.read_csv(result_path)
                
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

def create_plot(df, benchmarks, metric, output_dir):
    """Create grouped bar chart for the given metric"""
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Calculate bar positions
    n_variants = len(VARIANTS)
    width = 0.2  # Width of each bar
    variant_positions = np.arange(len(benchmarks))
    
    # Plot bars for each variant
    for i, (variant, hatch) in enumerate(zip(VARIANTS, hatches)):
        variant_data = df[df['variant'] == variant]
        cold_data = variant_data[variant_data['type'] == 'cold']
        hot_data = variant_data[variant_data['type'] == 'hot']
        
        # Plot cold and hot bars
        positions = variant_positions + (i - n_variants/2) * width
        cold_bars = ax.bar(positions, cold_data[metric], width / 2, label=f'{variant} (cold)',
                          color=palette[i], edgecolor='black', hatch=hatch)
        hot_bars = ax.bar(positions + width/2, hot_data[metric], width / 2 , label=f'{variant} (hot)',
                         color=palette[i + len(VARIANTS)], edgecolor='black', hatch=hatch)
    
    # Customize the plot
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    ax.set_xlabel('Benchmark', fontsize=TICKS_FONTSIZE)
    ax.set_xticks(variant_positions)
    xlabels = [benchmark.split('.')[1] for benchmark in benchmarks]
    ax.set_xticklabels(xlabels, rotation=0, fontsize=TICKS_FONTSIZE)
    # as labels are long, alternate their positions
    for i, label in enumerate(ax.get_xticklabels()):
        if i % 2 == 0:
            label.set_y(+0.03)  # Move slightly downward
        else:
            label.set_y(-0.03)  # Move slightly further downward
    
    title = 'Execution Time' if metric == 'exec_time' else 'Client Time'
    ax.set_title(title, pad=5, fontsize=TITLE_FONTSIZE)
    
    # Enhance legend
    legend = plt.legend(bbox_to_anchor=(0.01, 0.98), loc='upper left',
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_ylim(bottom=0)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_dir / (metric + '.pdf'), format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / (metric + '.png'), format='png', dpi=300, bbox_inches='tight')
    plt.close()

def main():
    # Load and process data
    df, common_benchmarks = load_and_process_data()
    
    # Create plots for exec_time and client_time
    create_plot(df, common_benchmarks, 'exec_time', 'output')
    create_plot(df, common_benchmarks, 'client_time', 'output')
    print("Plots saved in output directory")

if __name__ == "__main__":
    main()