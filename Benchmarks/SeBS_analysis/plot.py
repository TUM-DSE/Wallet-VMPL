#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import pprint as pprint
import subprocess

# Common graph settings
mpl.use("Agg")
mpl.rcParams["text.latex.preamble"] = r"\usepackage{amsmath}"
mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42
mpl.rcParams["font.family"] = "libertine"
sns.set_style("whitegrid")
sns.set_style("ticks", {"xtick.major.size": 8, "ytick.major.size": 8})
sns.set_context("paper", rc={"font.size": 5, "axes.titlesize": 5, "axes.labelsize": 8})

TITLE_FONTSIZE = 7
TICKS_FONTSIZE = 5
LEGEND_FONTSIZE = 5
ANNOTATION_SIZE = 4
figwidth = 3.3  # 3.3 inch for single column, 7 inch for double column
figheight = 2.0
VARIANTS = ['native', 'gramine', 'kata', 'vm', 'cvm', 'wallet_cow_prealloc', 'wallet_cow_no_prealloc', 'wallet_warm_cow_prealloc']
LABEL_MAPPINGS = {
    'native'  : 'Native',
    'gramine' : 'LibOS (Gramine)',
    'kata'    : 'Containers (Kata)',
    'vm'      : 'VM (KVM-Linux)',
    'cvm'     : 'CVM (SEV-SNP)',
    'wallet_cow_prealloc'  : 'Wallet',
    'wallet_cow_no_prealloc' : 'Wallet',
    'wallet_warm_cow_prealloc' : 'Wallet (warm)',
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

def crop_pdf(input_path):
    """Use pdfcrop to crop the PDF file."""
    try:
        subprocess.run(['pdfcrop', input_path, input_path], check=True)
        print(f"Successfully cropped {input_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error cropping PDF {input_path}: {e}")
    except FileNotFoundError:
        print("pdfcrop command not found. Please install texlive-extra-utils package.")

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

                
                cold_exec = df[cold_mask]['exec_time'].mean() / 1000 / 1000  # Convert μs to s
                cold_client = df[cold_mask]['client_time'].mean() / 1000 / 1000  # Convert μs to s
                hot_exec = df[hot_mask]['exec_time'].mean() / 1000 / 1000  # Convert μs to s
                hot_client = df[hot_mask]['client_time'].mean() / 1000 / 1000  # Convert μs to s
                
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

def plot_invocation_latency_cdf(df, variants, benchmarks, output_dir, collect_results=None):
    """Create CDF plots of invocation latencies for all variants"""
    
    # Storage for percentile and stddev data
    stats_results = []
    stats_results.append("\nInvocation Latency Statistics:")
    
    # Setup the plot
    fig, axes = plt.subplots(1, 2, figsize=(figwidth*2, figheight))
    titles = ["Cold Start Invocation Latency", "Warm Start Invocation Latency"]
    
    # for idx, exec_type in enumerate(["cold", "warm"]):
    for idx, exec_type in enumerate(["cold"]):
        ax = axes[idx]
        # Filter for the current execution type
        type_df = df[df['type'] == exec_type]
        
        stats_results.append(f"\n{titles[idx]}:")
        stats_results.append(f"{'Variant':<20} {'P50 (s)':<10} {'P99 (s)':<10} {'StdDev (s)':<10}")
        stats_results.append("-" * 50)
        
        # Plot CDF for each variant
        for i, variant in enumerate(variants):
            variant_data = type_df[type_df['variant'] == variant]
            
            if len(variant_data) == 0:
                continue
                
            # Sort the data for CDF
            latencies = variant_data['invocation_latency'].sort_values().values
            
            # Calculate P50, P99, and standard deviation
            if len(latencies) > 0:
                p50 = np.percentile(latencies, 50)
                p99 = np.percentile(latencies, 99)
                stddev = np.std(latencies)
                stats_results.append(f"{LABEL_MAPPINGS[variant]:<20} {p50:<10.6f} {p99:<10.6f} {stddev:<10.6f}")
            
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
    
    # Collect the statistics results if a collector is provided
    if collect_results is not None:
        collect_results.extend(stats_results)
    
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
    crop_pdf(output_dir / 'invocation_latency_cdf.pdf')
    
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
        crop_pdf(output_dir / f'invocation_latency_cdf_{exec_type}_linear.pdf')
        
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
    ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
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
    crop_pdf(output_dir / (filename + f'_{y_scale}.pdf'))

    plt.close()

def create_complete_plot_warm_hot(df, benchmarks, metric, output_dir, y_scale='linear'):
    """Create grouped bar chart with both warm and hot data for Wallet"""
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # We'll use hot data for standard variants as "warm"
    # For Wallet, we'll use wallet_warm_cow_prealloc for warm and wallet_cow_prealloc for hot
    warm_df = df[df['type'] == 'hot']  # Now using 'hot' for warm data for standard variants
    hot_df = df[df['type'] == 'hot']   # Still using 'hot' for Wallet hot data
    
    # Make sure we have Wallet warm variant in the dataframe
    wallet_warm_variant = 'wallet_warm_cow_prealloc'
    wallet_hot_variant = 'wallet_cow_prealloc'
    
    # Check if wallet_warm_variant exists in the dataframe
    if wallet_warm_variant not in df['variant'].unique():
        print(f"Warning: {wallet_warm_variant} not found in data. Using {wallet_hot_variant} for warm data.")
        # Fall back to using the hot variant for both warm and hot
        wallet_warm_data = warm_df[warm_df['variant'] == wallet_hot_variant]
    else:
        wallet_warm_data = df[df['variant'] == wallet_warm_variant]
    
    # Calculate geometric means for each variant
    warm_geomeans = {}
    hot_geomeans = {}
    
    # First calculate warm geomeans for standard variants (using hot data)
    for variant in VARIANTS:
        if variant != wallet_hot_variant:  # Skip Wallet since we'll handle it separately
            variant_warm_data = warm_df[warm_df['variant'] == variant]
            values = variant_warm_data[metric].values
            if len(values) > 0 and np.all(values > 0):
                warm_geomeans[variant] = np.exp(np.mean(np.log(values)))
            else:
                warm_geomeans[variant] = np.nan
    
    # For Wallet warm and hot, we need special handling
    # Find wallet warm data geomean
    if len(wallet_warm_data) > 0:
        # Get only the values for common benchmarks
        common_bench_warm_wallet = []
        for bench in benchmarks:
            bench_data = wallet_warm_data[wallet_warm_data['benchmark'] == bench]
            if len(bench_data) > 0:
                common_bench_warm_wallet.append(bench_data[metric].values[0])
        
        if len(common_bench_warm_wallet) > 0 and np.all(np.array(common_bench_warm_wallet) > 0):
            warm_geomeans[wallet_hot_variant] = np.exp(np.mean(np.log(common_bench_warm_wallet)))
        else:
            warm_geomeans[wallet_hot_variant] = np.nan
    else:
        warm_geomeans[wallet_hot_variant] = np.nan
        print(f"Warning: No data found for {wallet_warm_variant}")
    
    # Find wallet hot data
    wallet_hot_data = hot_df[hot_df['variant'] == wallet_hot_variant]
    if len(wallet_hot_data) > 0:
        values = wallet_hot_data[metric].values
        if len(values) > 0 and np.all(values > 0):
            hot_geomeans[wallet_hot_variant] = np.exp(np.mean(np.log(values)))
        else:
            hot_geomeans[wallet_hot_variant] = np.nan
    else:
        hot_geomeans[wallet_hot_variant] = np.nan
    
    # Add geomean data to display
    all_benchmarks = benchmarks + ['geomean']
    
    # Calculate bar positions
    n_variants = len(VARIANTS)
    width = 0.10  # Width of each bar
    variant_positions = np.arange(len(all_benchmarks))
    
    # Create labels with warm distinction for the legend
    variant_labels = []
    for variant in VARIANTS:
        if variant == wallet_hot_variant:
            variant_labels.append(f"{LABEL_MAPPINGS[variant]} (warm)")
        else:
            variant_labels.append(LABEL_MAPPINGS[variant])
    
    # Store bars for legend
    all_bars = []
    
    # Plot bars for each variant
    for i, variant in enumerate(VARIANTS):
        positions = variant_positions + (i - n_variants/2 + 0.5) * width
        
        # For standard variants, plot hot data as "warm"
        if variant != wallet_hot_variant:
            variant_warm_data = warm_df[warm_df['variant'] == variant]
            warm_values = []
            
            # Ensure we get data for each benchmark in the same order
            for bench in benchmarks:
                bench_data = variant_warm_data[variant_warm_data['benchmark'] == bench]
                if len(bench_data) > 0:
                    warm_values.append(bench_data[metric].values[0])
                else:
                    # Missing data point
                    warm_values.append(np.nan)
            
            # Add geomean at the end
            warm_values.append(warm_geomeans[variant])
            
            # Plot warm data for standard variants
            bars = ax.bar(positions, warm_values, width, 
                         label=variant_labels[i],
                         color=palette[i], edgecolor='black', hatch=hatches[i%len(hatches)])
            all_bars.append(bars)
        else:
            # For Wallet, plot warm data first
            wallet_warm_values = []
            
            # Ensure we get wallet warm data for each benchmark in the same order
            for bench in benchmarks:
                bench_data = wallet_warm_data[wallet_warm_data['benchmark'] == bench]
                if len(bench_data) > 0:
                    wallet_warm_values.append(bench_data[metric].values[0])
                else:
                    # Missing data point
                    wallet_warm_values.append(np.nan)
            
            # Add geomean at the end
            wallet_warm_values.append(warm_geomeans[variant])
            
            # Plot warm data for Wallet if we have data
            if len(wallet_warm_values) == len(positions):
                bars = ax.bar(positions, wallet_warm_values, width, 
                             label=variant_labels[i],
                             color=palette[i], edgecolor='black', hatch=hatches[i%len(hatches)])
                all_bars.append(bars)
            
            # Plot hot data for Wallet
            hot_values = []
            
            # Ensure we get hot data for each benchmark in the same order
            for bench in benchmarks:
                bench_data = wallet_hot_data[wallet_hot_data['benchmark'] == bench]
                if len(bench_data) > 0:
                    hot_values.append(bench_data[metric].values[0])
                else:
                    # Missing data point
                    hot_values.append(np.nan)
            
            # Add geomean at the end
            hot_values.append(hot_geomeans[variant])
            
            # Use a different color for hot data
            hot_color = 'tab:red'  # Different from the palette colors
            hot_bars = ax.bar(positions, hot_values, width, 
                            label=f"{LABEL_MAPPINGS[variant]} (hot)",
                            color=hot_color, edgecolor='black', hatch='xx')
            all_bars.append(hot_bars)
    
    # Customize the plot
    ax.set_yscale(y_scale)
    ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    ax.set_xticks(variant_positions)
    xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
    ax.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
    
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Create legend with custom ordering
    legend_bars = []
    legend_labels = []
    
    # Add all variants except Wallet hot
    for i, bars in enumerate(all_bars):
        if i == len(all_bars) - 1:  # Skip the last one (Wallet hot) for now
            continue
        legend_bars.append(bars)
        if i == len(VARIANTS) - 1:  # If this is Wallet warm
            legend_labels.append(f"{LABEL_MAPPINGS[wallet_hot_variant]} (warm)")
        else:
            legend_labels.append(variant_labels[i])
    
    # Add Wallet hot at the end
    legend_bars.append(all_bars[-1])
    legend_labels.append(f"{LABEL_MAPPINGS[wallet_hot_variant]} (hot)")
    
    # Create legend
    legend = ax.legend(legend_bars, legend_labels, 
                      bbox_to_anchor=(0.01, 0.98), loc='upper left',
                      borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    
    # Add gridlines
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    if(y_scale not in "log"):
        ax.set_ylim(bottom=0)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f'{metric}_warm_hot'
    plt.savefig(output_dir / (filename + f'_{y_scale}.pdf'), format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / (filename + f'_{y_scale}.png'), format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / (filename + f'_{y_scale}.pdf'))

    plt.close()

def create_complete_plot_wallet_variants(df, benchmarks, metric, output_dir, y_scale='linear'):
    """Create grouped bar chart with four different Wallet variants"""
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Define the wallet variants we want to plot
    wallet_variants = [
        ('wallet_cow_prealloc', 'cold', 'Wallet (cold)'),
        ('wallet_cow_prealloc', 'hot', 'Wallet (hot)'),
        ('wallet_warm_cow_prealloc', 'cold', 'Wallet (cold/warm)'),
        ('wallet_warm_cow_prealloc', 'hot', 'Wallet (warm)')
    ]
    
    # Use a different color palette for the wallet variants
    wallet_palette = sns.color_palette("husl", n_colors=len(wallet_variants))
    wallet_hatches = ["", "//", "xx", "\\\\"]
    
    # Calculate geometric means for each variant
    geomeans = {}
    for variant_name, exec_type, label in wallet_variants:
        variant_data = df[(df['variant'] == variant_name) & (df['type'] == exec_type)]
        
        # Calculate geometric mean (using log and exp to avoid numerical issues)
        values = []
        for bench in benchmarks:
            bench_data = variant_data[variant_data['benchmark'] == bench]
            if len(bench_data) > 0:
                values.append(bench_data[metric].values[0])
        
        # Avoid zeros or negative values for geometric mean
        if len(values) > 0 and np.all(np.array(values) > 0):
            geomean = np.exp(np.mean(np.log(np.array(values))))
            geomeans[(variant_name, exec_type)] = geomean
        else:
            # Fallback if there are zeros or negative values
            geomeans[(variant_name, exec_type)] = np.nan
    
    # Add geomean data to display
    all_benchmarks = benchmarks + ['geomean']
    
    # Calculate bar positions
    n_variants = len(wallet_variants)
    width = 0.15  # Width of each bar
    variant_positions = np.arange(len(all_benchmarks))
    
    # Store bars for legend
    all_bars = []
    
    # Plot bars for each variant
    for i, (variant_name, exec_type, label) in enumerate(wallet_variants):
        positions = variant_positions + (i - n_variants/2 + 0.5) * width
        
        variant_data = df[(df['variant'] == variant_name) & (df['type'] == exec_type)]
        values = []
        
        # Ensure we get data for each benchmark in the same order
        for bench in benchmarks:
            bench_data = variant_data[variant_data['benchmark'] == bench]
            if len(bench_data) > 0:
                values.append(bench_data[metric].values[0])
            else:
                # Missing data point
                values.append(np.nan)
        
        # Add geomean at the end
        values.append(geomeans.get((variant_name, exec_type), np.nan))
        
        # Plot data if we have enough values
        if len(values) == len(positions):
            bars = ax.bar(positions, values, width,
                         label=label,
                         color=wallet_palette[i], edgecolor='black', 
                         hatch=wallet_hatches[i % len(wallet_hatches)])
            all_bars.append(bars)
    
    # Customize the plot
    ax.set_yscale(y_scale)
    ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    ax.set_xticks(variant_positions)
    xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
    ax.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
    
    ax.set_title('Wallet Variants Comparison (lower is better ↓)', 
                 pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Create legend
    legend = ax.legend(bbox_to_anchor=(0.01, 0.98), loc='upper left',
                      borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    
    # Add gridlines
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    if y_scale not in "log":
        ax.set_ylim(bottom=0)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f'{metric}_wallet_variants'
    plt.savefig(output_dir / (filename + f'_{y_scale}.pdf'), format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / (filename + f'_{y_scale}.png'), format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / (filename + f'_{y_scale}.pdf'))

    plt.close()

def print_performance_comparison(df, benchmarks, metric, exec_type, collect_results=None):
    """
    Print geometric means and calculate how much percent Wallet is better or worse than other baselines
    
    If collect_results is provided, results will be stored there for later display.
    """
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
    
    # Store or print the results
    result_lines = []
    result_lines.append(f"\n{metric} ({exec_type} start) - Geometric Means:")
    for variant in VARIANTS:
        result_lines.append(f"  {LABEL_MAPPINGS[variant]}: {geomeans[variant]:.6f} s")
    
    # Get the Wallet value
    wallet_variant = 'wallet_cow_prealloc'
    wallet_value = geomeans.get(wallet_variant)
    
    if wallet_value is None:
        result_lines.append(f"No data for Wallet in {metric} ({exec_type} start)")
    else:
        # Compare Wallet with other variants
        result_lines.append(f"\n{metric} ({exec_type} start) - Wallet Comparison:")
        for variant in VARIANTS:
            if variant != wallet_variant:
                baseline_value = geomeans.get(variant)
                if baseline_value is not None and not np.isnan(baseline_value):
                    # Calculate percentage difference: (wallet - baseline) / baseline * 100
                    pct_diff = (wallet_value - baseline_value) / baseline_value * 100
                    comparison = "slower" if pct_diff > 0 else "faster"
                    result_lines.append(f"  Wallet is {abs(pct_diff):.2f}% {comparison} than {LABEL_MAPPINGS[variant]}")
                else:
                    result_lines.append(f"  No data for {LABEL_MAPPINGS[variant]}")
    
    # If collect_results is provided, add the results there
    if collect_results is not None:
        collect_results.extend(result_lines)
    
    # Also print immediately if needed
    # for line in result_lines:
    #     print(line)

def create_side_by_side_plot(df, benchmarks, output_dir):
    """Create side-by-side subplots for client_time with cold and hot execution types"""
    fig, axes = plt.subplots(1, 2, figsize=(7, figheight), sharey=True)
    
    exec_types = ['cold', 'hot']
    titles = ['(a) Cold Start', '(b) Warm Start']
    all_bars = []  # Store bars for shared legend
    
    for idx, exec_type in enumerate(exec_types):
        ax = axes[idx]
        # Filter data for the specific execution type
        filtered_df = df[df['type'] == exec_type]
        
        # Calculate bar positions
        n_variants = len(VARIANTS)
        width = 0.12  # Width of each bar
        variant_positions = np.arange(len(benchmarks))
        
        # Plot bars for each variant
        for i, variant in enumerate(VARIANTS):
            variant_data = filtered_df[filtered_df['variant'] == variant]
            # Prepare data excluding geomean
            values = []
            for bench in benchmarks:
                bench_data = variant_data[variant_data['benchmark'] == bench]
                if len(bench_data) > 0:
                    values.append(bench_data['client_time'].values[0])
                else:
                    values.append(np.nan)
                    
            positions = variant_positions + (i - n_variants/2 + 0.5) * width
            bars = ax.bar(positions, values, width, 
                         label=LABEL_MAPPINGS[variant],
                         color=palette[i], edgecolor='black', hatch=hatches[i%len(hatches)])
            
            # Only store bars for legend from the first subplot
            if idx == 0:
                all_bars.append(bars[0])
        
        # Customize the subplot
        ax.set_yscale('log')
        ax.set_title(titles[idx], fontsize=TITLE_FONTSIZE)
        ax.set_xticks(variant_positions)
        xlabels = [benchmark.split('.')[1] for benchmark in benchmarks]
        ax.set_xticklabels(xlabels, rotation=15, fontsize=TICKS_FONTSIZE)
        ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
        
        # Only add y-label to the first subplot
        if idx == 0:
            ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
        
        # Add gridlines
        ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    # Add a shared legend below the subplots
    fig.legend(all_bars, [LABEL_MAPPINGS[variant] for variant in VARIANTS], 
              loc='lower center', bbox_to_anchor=(0.5, -0.12),
              ncol=len(VARIANTS), fontsize=LEGEND_FONTSIZE)
    
    # Add an overall title indicating log scale
    #fig.suptitle('Client Time (Lower is better ↓)', fontsize=TITLE_FONTSIZE+1, y=0.98)
    fig.suptitle('Lower is better ↓', fontsize=TITLE_FONTSIZE, y=0.98, color='navy')
    
    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.2)  # Make room for the legend
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'client_time_cold_hot.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'client_time_cold_hot.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / 'client_time_cold_hot.pdf')
    
    plt.close()

def main():
    global VARIANTS
    # Storage for all performance comparison results
    all_comparison_results = []
    
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
            # Collect performance comparison results instead of printing immediately
            print_performance_comparison(df, common_benchmarks, metric, exec_type, all_comparison_results)
    
    # Create combined warm/hot plots for each metric
    for metric in metrics:
        create_complete_plot_warm_hot(df, common_benchmarks, metric, 'output')
        create_complete_plot_warm_hot(df, common_benchmarks, metric, 'output', 'log')
        
    # Create wallet variant comparison plots
    for metric in metrics:
        create_complete_plot_wallet_variants(df, common_benchmarks, metric, 'output')
        create_complete_plot_wallet_variants(df, common_benchmarks, metric, 'output', 'log')
    
    # Create side-by-side plot for client_time (cold and hot)
    create_side_by_side_plot(df, common_benchmarks, 'output')

    # Load and process data and derive the invocation latency values
    VARIANTS = ['native', 'gramine', 'kata', 'vm', 'cvm', 'wallet_cow_prealloc']
    df, common_benchmarks = derive_incovation_data()
    print(df, common_benchmarks)
    # Create invocation latency CDF plots
    plot_invocation_latency_cdf(df, VARIANTS, common_benchmarks, 'output', all_comparison_results)
    
    print("Plots saved in output directory")
    
    # Print all performance comparison results at the end
    print("\n" + "="*50)
    print("PERFORMANCE COMPARISON SUMMARY")
    print("="*50)
    for line in all_comparison_results:
        print(line)
    print("="*50)

if __name__ == "__main__":
    main()
