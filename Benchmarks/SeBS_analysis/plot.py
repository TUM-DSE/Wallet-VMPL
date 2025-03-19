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

TITLE_FONTSIZE = 8
TICKS_FONTSIZE = 7
LEGEND_FONTSIZE = 6
ANNOTATION_SIZE = 4
figwidth = 4.3  # 3.3 inch for single column, 7 inch for double column
figheight = 2.2
VARIANTS = ['native', 'gramine', 'vm', 'kata', 'cvm', 'wallet_cow_prealloc', 'wallet_cow_no_prealloc']
LABEL_MAPPINGS = {
    'native'  : 'Native',
    'gramine' : 'Gramine',
    'vm'      : 'VM',
    'kata'    : 'Kata',
    'cvm'     : 'CVM',
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

    invocation_latency(VARIANTS, common_benchmarks)
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

def invocation_latency(variants, benchmarks):
    import json
    from datetime import datetime
    output_file_path = Path("output/invocation_latency.csv")
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
                            output_file.write(f"{variant},{bench},{bench_type},{abs(end-start)}\n")
                    else:
                        print(f"Missing _invocations in {result_path}")
                        exit()
                else:
                    print(f"Result path {result_path} not found")
                    exit()
    output_file.close()
    df = pd.read_csv(output_file_path)
    mean_output_path = Path("output/invocation_latency_mean.csv")
    mean_output = open(mean_output_path, "w")
    mean_output.write("variant,benchmark,type,invocation_latency\n")
    for variant in variants:
        for bench in benchmarks:
            for bench_type in bench_types:
                e = df[df["variant"] == variant]
                e = e[e["benchmark"] == bench]
                e = e[e["type"] == bench_type]
                m = e["invocation_latency"].mean()
                mean_output.write(f"{variant},{bench},{bench_type},{m}\n")

    mean_output.close()
    df = pd.read_csv(mean_output_path)
    return
    for exec_type in ["cold", "sequential"]:
        create_inv_lat_plot(df, benchmarks, exec_type, "output")
        create_inv_lat_plot(df, benchmarks, exec_type, "output", 'log')



def create_inv_lat_plot(df, benchmarks, exec_type, output_dir, y_scale='linear'):
    """Create grouped bar chart for the given metric and execution type"""
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    metric = "invocation_latency"
    # Filter data for the specific execution type
    df = df[df['type'] == exec_type]
    # Calculate bar positions
    n_variants = len(VARIANTS)
    width = 0.10  # Width of each bar
    variant_positions = np.arange(len(benchmarks))

    # Plot bars for each variant
    for i, variant in enumerate(VARIANTS):
        variant_data = df[df['variant'] == variant]
        positions = variant_positions + (i - n_variants/2 + 0.5) * width
        bars = ax.bar(positions, variant_data[metric], width,
                     label=LABEL_MAPPINGS[variant],
                     color=palette[i], edgecolor='black', hatch=hatches[i%len(hatches)])

    # Customize the plot
    ax.set_yscale(y_scale)
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

    filename = f'invocation_latency_{exec_type}'
    plt.savefig(output_dir / (filename + f'_{y_scale}.pdf'), format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / (filename + f'_{y_scale}.png'), format='png', dpi=300, bbox_inches='tight')

    plt.close()


def create_complete_plot(df, benchmarks, metric, exec_type, output_dir, y_scale='linear', name=""):
    """Create grouped bar chart for the given metric and execution type"""
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Filter data for the specific execution type
    df = df[df['type'] == exec_type]
    
    # Calculate bar positions
    n_variants = len(VARIANTS)
    width = 0.10  # Width of each bar
    if name == "comp":
        width = 0.30
    variant_positions = np.arange(len(benchmarks))

    # Plot bars for each variant
    for i, variant in enumerate(VARIANTS):
        variant_data = df[df['variant'] == variant]
        positions = variant_positions + (i - n_variants/2 + 0.5) * width
        #print(variant_data[metric])
        bars = ax.bar(positions, variant_data[metric], width, 
                     label=LABEL_MAPPINGS[variant],
                     color=palette[i], edgecolor='black', hatch=hatches[i%len(hatches)])
    
    # Customize the plot
    ax.set_yscale(y_scale)
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
    if name == "comp":
        plt.savefig(output_dir / (filename + f'_comp_{y_scale}.pdf'), format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(output_dir / (filename + f'_comp_{y_scale}.png'), format='png', dpi=300, bbox_inches='tight')
    else:
        plt.savefig(output_dir / (filename + f'_{y_scale}.pdf'), format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(output_dir / (filename + f'_{y_scale}.png'), format='png', dpi=300, bbox_inches='tight')

    plt.close()

def main():
    global VARIANTS
    # Load and process data
    df, common_benchmarks = load_and_process_data()

    #diff_csv(df)
    # Create separate plots for each metric and execution type
    metrics = ['exec_time', 'client_time']
    exec_types = ['cold', 'hot']

    old_df = df

    filter = df["variant"].str.contains("no_prealloc")
    df = df[~filter]
    VARIANTS = ['native', 'gramine', 'vm', 'kata', 'cvm', 'wallet_cow_prealloc']

    for metric in metrics:
        for exec_type in exec_types:
            create_complete_plot(df, common_benchmarks, metric, exec_type, 'output')
            create_complete_plot(df, common_benchmarks, metric, exec_type, 'output', 'log')

    VARIANTS = ['wallet_cow_prealloc', 'wallet_cow_no_prealloc']
    filter = old_df["variant"].str.contains("wallet")
    df = old_df[filter]
    LABEL_MAPPINGS['wallet_cow_prealloc']  = 'Wallet (preallocation)'
    for metric in metrics:
        for exec_type in exec_types:
            create_complete_plot(df, common_benchmarks, metric, exec_type, 'output', "linear", "comp")
            create_complete_plot(df, common_benchmarks, metric, exec_type, 'output', 'log', "comp")



    print("Plots saved in output directory")

def diff_csv(df):

    for w in ["wallet", "wallet_"]:
        lr = []

        for b in BENCHMARKS:
            if b in "220.video-processing":
                continue
            d = df[df["benchmark"] == b]
            dc = d[d["variant"] == "cvm"]
            dw = d[d["variant"] == w]
            for e in ["hot", "cold"]:
                f = dc[dc["type"] == e]["client_time"]
                g = dw[dw["type"] == e]["client_time"]
                cc = float(f.iloc[0])
                cw = float(g.iloc[0])
                t = cc / cw * 100
                lr.append((b,e,t))
        p = pd.DataFrame(lr, columns = ["benchmark","type","diff"])

        p.to_csv(f"output/{w}.csv")

if __name__ == "__main__":
    main()
