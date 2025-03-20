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
VARIANTS = ['wallet_', 'wallet_cow_prealloc']
LABEL_MAPPINGS = {
    'wallet_' : 'Wallet - CoW Disabled',
    'wallet_cow_prealloc'  : 'Wallet - CoW Enabled',
}

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer', 
    '311.compression',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    '504.dna-visualisation'
]
palette = sns.color_palette("pastel", n_colors=len(VARIANTS*2))
hatches = ["", "//", "xx", "\\\\", ".."]
linestyles = ["-", "--", "-.", ":", "-"]

INVOCATION_LATENCY_PATH="output/invocation_latency_cow.csv"
INVOCATION_LATENCY_MEAN_PATH="output/invocation_latency_mean_cow.csv"

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

def derive_incovation_data():
    """Load and process data from all variants and benchmarks to derive the invocation latency data"""
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

    df = invocation_latency(VARIANTS, common_benchmarks)
    return df, list(common_benchmarks) 

def invocation_latency(variants, benchmarks):
    import json
    from datetime import datetime
    output_file_path = Path(INVOCATION_LATENCY_PATH)
    output_file = open(output_file_path, "w")
    output_file.write("variant,benchmark,type,invocation_latency\n")
    bench_types = ["cold", "warm"]
    for variant in variants:
        print(variant)
        for bench in benchmarks:
            print(bench)
            for bench_type in bench_types:
                result_path = Path(f"./results/{variant}/{bench}/perf-cost/{bench_type}_results-processed.json")
                if not result_path.exists():
                    if bench_type == "warm":
                        result_path = Path(f"./results/{variant}/{bench}/perf-cost/sequential_results-processed.json")
                if result_path.exists():
                    with open(result_path) as f:
                        d = json.load(f)
                    if d.get("_invocations"):
                        d = d["_invocations"]
                        d = d[list(d.keys())[0]]
                        for k in d.keys():
                            e = d[k]
                            start = datetime.strptime(e["times"]["client_begin"], "%Y-%m-%d %H:%M:%S.%f").timestamp()
                            end = float(e["output"]["begin"])
                            if (end < start):
                              print("--------------------")
                              print(result_path)
                              print("start " + datetime.fromtimestamp(start).strftime('%Y-%m-%d %H:%M:%S.%f'))     
                              print("end " + datetime.fromtimestamp(end).strftime('%Y-%m-%d %H:%M:%S.%f'))
                              print(end-start)
                              print("--------------------")
                                              
                            output_file.write(f"{variant},{bench},{bench_type},{end-start}\n")
                    else:
                        print(f"Missing _invocations in {result_path}")
                        exit()
                else:
                    print(f"Result path {result_path} not found")
                    exit()
    output_file.close()
    
    # return the original invocation latencies (without taking the mean)
    # to create the CDF plots
    df = pd.read_csv(output_file_path)
    return df

def plot_wallet_invocation_latency_cdf(df, output_dir):
    """Create CDF plots comparing just wallet variants for both invocation latency and client time"""
    wallet_variants = ['wallet_', 'wallet_cow_prealloc']
    
    # Update labels for clarity
    custom_labels = {
        'wallet_cow_prealloc': 'Wallet (CoW enabled)',
        'wallet_': 'Wallet (CoW disabled)'
    }
    
    # Setup color palette for just these two variants
    wallet_palette = palette
    
    # Filter data for just these variants
    wallet_df = df[df['variant'].isin(wallet_variants)]
    
    # Plot invocation latency CDF
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    color_idx = 0
    for idx, exec_type in enumerate(["cold", "warm"]):
        # Filter for the current execution type
        type_df = wallet_df[wallet_df['type'] == exec_type]
        
        # Plot CDF for each wallet variant
        for i, variant in enumerate(wallet_variants):
            variant_data = type_df[type_df['variant'] == variant]
            
            if len(variant_data) == 0:
                continue
                
            # Sort the data for CDF
            latencies = variant_data['invocation_latency'].sort_values().values
            # Create CDF points
            y_values = np.arange(1, len(latencies) + 1) / len(latencies)
            
            # Plot the CDF
            ax.plot(latencies, y_values, label=f"{custom_labels[variant]} - {exec_type} start", 
                    color=wallet_palette[color_idx], linewidth=1.5, alpha=1, linestyle=linestyles[color_idx%len(linestyles)])
            color_idx+=1
            
    # Add horizontal lines at specific percentiles
    percentiles = [0.5, 0.95, 0.99]
    for p in percentiles:
        ax.axhline(y=p, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
        ax.text(ax.get_xlim()[1]*0.98, p, f"{int(p*100)}%", 
                verticalalignment='bottom', horizontalalignment='right', 
                fontsize=ANNOTATION_SIZE)
    
    # Customize the plot
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    ax.set_xlabel('Latency (seconds)', fontsize=TICKS_FONTSIZE)
    ax.set_ylabel('Cumulative Probability', fontsize=TICKS_FONTSIZE)
    ax.set_ylim(0, 1.05)
    ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Add legend
    ax.legend(fontsize=LEGEND_FONTSIZE, loc='lower right')
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    plt.savefig(output_dir / 'wallet_invocation_latency_cdf_linear.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'wallet_invocation_latency_cdf_linear.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def plot_wallet_comparison_stacked_bars(df, benchmarks, output_dir):
    """Create stacked bar chart for wallet variants only"""
    wallet_variants = ['wallet_', 'wallet_cow_prealloc']
    
    # Update labels for clarity
    custom_labels = {
        'wallet_cow_prealloc': 'Wallet (CoW enabled)',
        'wallet_': 'Wallet (CoW disabled)'
    }
    
    # Filter data for just these wallet variants
    wallet_df = df[df['variant'].isin(wallet_variants)]
    
    # Set up the color palette for just these two variants
    wallet_palette = palette
    
    # Create plots for each execution type
    for exec_type in ['cold', 'hot']:
        fig, ax = plt.subplots(figsize=(figwidth, figheight))
        
        # Filter data for the specific execution type
        filtered_df = wallet_df[wallet_df['type'] == exec_type]
        
        # Calculate geometric means for each variant
        geomeans = {}
        for variant in wallet_variants:
            variant_data = filtered_df[filtered_df['variant'] == variant]
            # Calculate geometric mean (using log and exp to avoid numerical issues)
            values = variant_data['client_time'].values
            # Avoid zeros or negative values for geometric mean
            if np.all(values > 0):
                geomean = np.exp(np.mean(np.log(values)))
                geomeans[variant] = geomean
            else:
                # Fallback if there are zeros or negative values
                geomeans[variant] = np.nan
        
        # Add geomean data to display
        all_benchmarks = benchmarks + ['geomean']
        
        # Calculate bar positions
        n_variants = len(wallet_variants)
        width = 0.20  # Width of each bar
        variant_positions = np.arange(len(all_benchmarks))
        
        # Plot bars for each variant
        for i, variant in enumerate(wallet_variants):
            variant_data = filtered_df[filtered_df['variant'] == variant]
            # Prepare data including geomean
            values = []
            for bench in benchmarks:
                bench_data = variant_data[variant_data['benchmark'] == bench]
                if not bench_data.empty:
                    values.append(bench_data['client_time'].values[0])
                else:
                    values.append(np.nan)
            values.append(geomeans[variant])  # Add geomean value at the end
            
            positions = variant_positions + (i - n_variants/2 + 0.5) * width
            bars = ax.bar(positions, values, width, 
                         label=custom_labels[variant],
                         color=wallet_palette[i])
        
        # Customize the plot
        ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
        plt.yticks(fontsize=TICKS_FONTSIZE)
        ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
        ax.set_xticks(variant_positions)
        xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
        ax.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
        
        # Title and styling
        ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
        
        # Add legend
        legend = plt.legend(loc='upper right',
                           fontsize=LEGEND_FONTSIZE)
        
        # Add gridlines
        ax.yaxis.grid(True, linestyle='--', alpha=0.7)
        ax.set_ylim(bottom=0)
        
        # Adjust layout
        plt.tight_layout()
        
        # Save plot (linear scale)
        plt.savefig(output_dir / f'wallet_client_time_cow_{exec_type}.pdf', format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(output_dir / f'wallet_client_time_cow_{exec_type}.png', format='png', dpi=300, bbox_inches='tight')
        
        plt.close()

def plot_wallet_comparison_grouped_bars(df, benchmarks, output_dir):
    """Create grouped bar charts for wallet variants, including a log-scale version."""
    
    wallet_variants = ['wallet_', 'wallet_cow_prealloc']
    exec_types = ['cold', 'hot']
    
    # Define labels and order
    custom_labels = {
        'wallet_': 'CoW Disabled',
        'wallet_cow_prealloc': 'CoW Enabled'
    }
    colors_group = [None] * len(VARIANTS*2)
    colors_group[0] = palette[0]
    colors_group[1] = palette[0]
    colors_group[2] = palette[1]
    colors_group[3] = palette[1]
    hatches_group = ['', '//', '', '//']
    
    # Filter only the relevant data
    wallet_df = df[df['variant'].isin(wallet_variants)]
    
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Benchmarks + Geometric Mean
    all_benchmarks = benchmarks + ['geomean']
    
    # Bar positions and widths
    n_variants = len(wallet_variants) * len(exec_types)  # 4 bars per benchmark
    width = 0.15  # Bar width
    positions = np.arange(len(all_benchmarks))  # X positions
    
    bar_positions = []
    
    colors = palette
    
    # Iterate in new order: Cold first, then Hot
    for j, exec_type in enumerate(exec_types):  # cold, hot
        for i, variant in enumerate(wallet_variants):  # CoW Disabled, CoW Enabled
            # Shift bar positions for correct alignment
            offset = ((j * len(wallet_variants) + i) - n_variants / 2 + 0.5) * width
            variant_exec_df = wallet_df[(wallet_df['variant'] == variant) & (wallet_df['type'] == exec_type)]
            
            values = []
            for bench in benchmarks:
                bench_data = variant_exec_df[variant_exec_df['benchmark'] == bench]
                values.append(bench_data['client_time'].values[0] if not bench_data.empty else np.nan)
            
            # Compute geomean
            geomean = np.exp(np.mean(np.log(values))) if np.all(np.array(values) > 0) else np.nan
            values.append(geomean)
            
            # Plot bars
            label = f"{exec_type.capitalize()} - {custom_labels[variant]}"
            ax.bar(positions + offset, values, width, label=label, color=colors_group[i*2], hatch=hatches_group[j], edgecolor='black')
            
            bar_positions.append(positions + offset)
    
    # Customize plot
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    ax.set_xticks(positions)
    xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
    ax.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
    
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Legend
    ax.legend(loc='upper right', fontsize=LEGEND_FONTSIZE)
    
    # Grid and formatting
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_ylim(bottom=0)
    
    # Save linear-scale plot
    output_dir = Path(output_dir)
    plt.tight_layout()
    plt.savefig(output_dir / 'wallet_client_time_grouped.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'wallet_client_time_grouped.png', format='png', dpi=300, bbox_inches='tight')
    
    # Create log-scale version
    fig_log, ax_log = plt.subplots(figsize=(figwidth, figheight))
    
    for i, (bar_pos, label) in enumerate(zip(bar_positions, ax.get_legend().get_texts())):
        values = [bar.get_height() for bar in ax.patches[i::n_variants]]
        ax_log.bar(bar_pos, values, width, label=label.get_text(), color=colors_group[i], hatch=hatches_group[i], edgecolor='black')
    
    ax_log.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    ax_log.set_xticks(positions)
    ax_log.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
    
    ax_log.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    ax_log.set_yscale('log')
    ax_log.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    ax_log.legend(loc='upper right', fontsize=LEGEND_FONTSIZE)
    
    # Save log-scale plot
    plt.tight_layout()
    plt.savefig(output_dir / 'wallet_client_time_grouped_log.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'wallet_client_time_grouped_log.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close(fig)
    plt.close(fig_log)

def main():
    global VARIANTS

    # Add wallet variant comparison plots
    VARIANTS = ['wallet_', 'wallet_cow_prealloc']
    
    # Get data for invocation latency CDF
    invocation_df, common_benchmarks = derive_incovation_data()
    
    # Get data for client time bar plots
    client_df, _ = load_and_process_data()
    
    output_dir = Path('output')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create invocation latency CDF
    plot_wallet_invocation_latency_cdf(invocation_df, output_dir)
    
    # Create client time bar plots
    plot_wallet_comparison_stacked_bars(client_df, common_benchmarks, output_dir)
    plot_wallet_comparison_grouped_bars(client_df, common_benchmarks, output_dir)
    
    print("Wallet comparison plots saved in output directory")

if __name__ == "__main__":
    main()
