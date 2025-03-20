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

INVOCATION_LATENCY_PATH="output/invocation_latency.csv"
INVOCATION_LATENCY_MEAN_PATH="output/invocation_latency_mean.csv"

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
    bench_types = ["cold"] #excluded warm because of non-synced time measurements in/out of the CVM
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
    # Calculate the mean invocation latency for each variant, benchmark, and type
    # df = pd.read_csv(output_file_path)
    # mean_output_path = Path(INVOCATION_LATENCY_MEAN_PATH)
    # mean_output = open(mean_output_path, "w")
    # mean_output.write("variant,benchmark,type,invocation_latency\n")
    # for variant in variants:
    #     for bench in benchmarks:
    #         for bench_type in bench_types:
    #             e = df[df["variant"] == variant]
    #             e = e[e["benchmark"] == bench]
    #             e = e[e["type"] == bench_type]
    #             m = e["invocation_latency"].mean()
    #             mean_output.write(f"{variant},{bench},{bench_type},{m}\n")
    # mean_output.close()
    
    # return the original invocation latencies (without taking the mean)
    # to create the CDF plots
    df = pd.read_csv(output_file_path)
    return df

def plot_invocation_latency_cdf(df, variants, benchmarks, output_dir):
    """Create CDF plots of invocation latencies for all variants"""
    
    # Setup the plot
    fig, axes = plt.subplots(1, 2, figsize=(figwidth*2, figheight))
    titles = ["Cold Start Invocation Latency", "Warm Start Invocation Latency"]
    
    # for idx, exec_type in enumerate(["cold", "warm"]):
    for idx, exec_type in enumerate(["cold"]):
        ax = axes[idx]
        # Filter for the current execution type
        type_df = df[df['type'] == exec_type]
        
        # Plot CDF for each variant
        for i, variant in enumerate(variants):
            variant_data = type_df[type_df['variant'] == variant]
            
            if len(variant_data) == 0:
                continue
                
            # Sort the data for CDF
            latencies = variant_data['invocation_latency'].sort_values().values
            # Create CDF points
            y_values = np.arange(1, len(latencies) + 1) / len(latencies)
            
            # Plot the CDF
            ax.plot(latencies, y_values, label=LABEL_MAPPINGS[variant], 
                    color=palette[i], linewidth=1.5, alpha=1, linestyle=linestyles[i%len(linestyles)])
        
        # Add horizontal lines at specific percentiles
        percentiles = [0.5, 0.95, 0.99]
        for p in percentiles:
            ax.axhline(y=p, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
            ax.text(ax.get_xlim()[1]*0.98, p, f"{int(p*100)}%", 
                    verticalalignment='bottom', horizontalalignment='right', 
                    fontsize=ANNOTATION_SIZE)
        
        # Customize the plot
        ax.set_title(titles[idx], fontsize=TITLE_FONTSIZE)
        ax.set_xlabel('Latency (seconds)', fontsize=TICKS_FONTSIZE)
        ax.set_ylabel('Cumulative Probability', fontsize=TICKS_FONTSIZE)
        ax.set_ylim(0, 1.05)
        ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
        ax.grid(True, linestyle='--', alpha=0.7)
        
        # Add log scale option for x-axis
        ax.set_xscale('log')
        
    # Add a single legend for both plots
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(0.5, -0.1),
              ncol=len(variants), fontsize=LEGEND_FONTSIZE)
    
    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.2)  # Make room for the legend
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'invocation_latency_cdf.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'invocation_latency_cdf.png', format='png', dpi=300, bbox_inches='tight')
    
    # Also create individual CDFs with linear scale
    
    # for idx, exec_type in enumerate(["cold", "warm"]):
    for idx, exec_type in enumerate(["cold"]):
        fig, ax = plt.subplots(figsize=(figwidth, figheight))
        
        # Filter for the current execution type
        type_df = df[df['type'] == exec_type]
        
        # Plot CDF for each variant
        for i, variant in enumerate(variants):
            variant_data = type_df[type_df['variant'] == variant]
            
            if len(variant_data) == 0:
                continue
                
            # Sort the data for CDF
            latencies = variant_data['invocation_latency'].sort_values().values
            # Create CDF points
            y_values = np.arange(1, len(latencies) + 1) / len(latencies)
            
            # Plot the CDF
            ax.plot(latencies, y_values, label=LABEL_MAPPINGS[variant], 
                    color=palette[i], linewidth=1.5, alpha=1, linestyle=linestyles[i%len(linestyles)])
        
        # Add horizontal lines at specific percentiles
        percentiles = [0.5, 0.95, 0.99]
        for p in percentiles:
            ax.axhline(y=p, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
            ax.text(ax.get_xlim()[1]*0.98, p, f"{int(p*100)}%", 
                    verticalalignment='bottom', horizontalalignment='right', 
                    fontsize=ANNOTATION_SIZE)
        
        # Customize the plot
        ax.set_title(titles[idx], fontsize=TITLE_FONTSIZE)
        ax.set_xlabel('Latency (seconds)', fontsize=TICKS_FONTSIZE)
        ax.set_ylabel('Cumulative Probability', fontsize=TICKS_FONTSIZE)
        ax.set_ylim(0, 1.05)
        ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
        ax.grid(True, linestyle='--', alpha=0.7)
        
        # Add legend
        ax.legend(fontsize=LEGEND_FONTSIZE, loc='lower right', bbox_to_anchor=(0.85, 0.08))
        
        # Adjust layout
        plt.tight_layout()
        
        # Save plot
        plt.savefig(output_dir / f'invocation_latency_cdf_{exec_type}_linear.pdf', format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(output_dir / f'invocation_latency_cdf_{exec_type}_linear.png', format='png', dpi=300, bbox_inches='tight')
        
        plt.close()

def create_complete_plot(df, benchmarks, metric, exec_type, output_dir, y_scale='linear'):
    """Create grouped bar chart for the given metric and execution type"""
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Filter data for the specific execution type
    filtered_df = df[df['type'] == exec_type]
    # Calculate geometric means for each variant
    geomeans = {}
    for variant in VARIANTS:
        variant_data = filtered_df[filtered_df['variant'] == variant]
        # Calculate geometric mean (using log and exp to avoid numerical issues)
        values = variant_data[metric].values
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
    n_variants = len(VARIANTS)
    width = 0.10  # Width of each bar
    variant_positions = np.arange(len(all_benchmarks))

    # Plot bars for each variant
    for i, variant in enumerate(VARIANTS):
        variant_data = filtered_df[filtered_df['variant'] == variant]
        # Prepare data including geomean
        values = list(variant_data[metric].values)
        values.append(geomeans[variant])  # Add geomean value at the end
        
        positions = variant_positions + (i - n_variants/2 + 0.5) * width
        #print(variant_data[metric])
        bars = ax.bar(positions, values, width, 
                     label=LABEL_MAPPINGS[variant],
                     color=palette[i], edgecolor='black', hatch=hatches[i%len(hatches)])
    
    # Customize the plot
    ax.set_yscale(y_scale)
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    # ax.set_xlabel('Benchmark', fontsize=TICKS_FONTSIZE)
    ax.set_xticks(variant_positions)
    xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
    ax.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
    # ax.set_xticklabels(xlabels, rotation=0, fontsize=TICKS_FONTSIZE)
    # # as labels are long, alternate their positions
    # for i, label in enumerate(ax.get_xticklabels()):
    #     if i % 2 == 0:
    #         label.set_y(+0.03)  # Move slightly downward
    #     else:
    #         label.set_y(-0.03)  # Move slightly further downward
    
    # title = f'{metric.replace("_", " ").title()} ({exec_type} start)'
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    legend = plt.legend(bbox_to_anchor=(0.01, 0.98), loc='upper left',
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    # legend.get_frame().set_edgecolor('black')
    
    # Add gridlines
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    if(y_scale not in "log"):
        ax.set_ylim(bottom=0)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f'{metric}_{exec_type}'
    plt.savefig(output_dir / (filename + f'_{y_scale}.pdf'), format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / (filename + f'_{y_scale}.png'), format='png', dpi=300, bbox_inches='tight')

    plt.close()

def main():
    global VARIANTS
    # Load and process data
    df, common_benchmarks = load_and_process_data()

    # Create separate plots for each metric and execution type
    metrics = ['exec_time', 'client_time']
    exec_types = ['cold', 'hot']

    filter = df["variant"].str.contains("no_prealloc")
    df = df[~filter]
    VARIANTS = ['native', 'gramine', 'kata', 'vm', 'cvm', 'wallet_cow_prealloc']

    for metric in metrics:
        for exec_type in exec_types:
            create_complete_plot(df, common_benchmarks, metric, exec_type, 'output')
            create_complete_plot(df, common_benchmarks, metric, exec_type, 'output', 'log')

    # Load and process data and derive the invocation latency values
    VARIANTS = ['native', 'gramine', 'kata', 'vm', 'cvm', 'wallet_cow_prealloc']
    df, common_benchmarks = derive_incovation_data()
    print(df, common_benchmarks)
    # Create invocation latency CDF plots
    plot_invocation_latency_cdf(df, VARIANTS, common_benchmarks, 'output')
    
    print("Plots saved in output directory")

if __name__ == "__main__":
    main()
