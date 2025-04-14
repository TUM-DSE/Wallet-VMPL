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
#VARIANTS = ['wallet', 'wallet_cow_prealloc']
#VARIANTS = ['wallet_cow_prealloc', 'wallet_no_cow_prealloc', 'wallet_warm_cow_prealloc', 'wallet_warm_no_cow_prealloc']
VARIANTS = ['wallet_cow_prealloc', 'wallet_no_cow_prealloc', 'wallet_warm_cow_prealloc']
LABEL_MAPPINGS = {
    #'wallet' : 'Wallet - CoW Disabled',
    'wallet_cow_prealloc' : 'Wallet - CoW Disabled',
    'wallet_no_cow_prealloc'  : 'Wallet - CoW Enabled',
    'wallet_warm_cow_prealloc'  : 'Wallet (lukewarm) - CoW Enabled',
    'wallet_warm_no_cow_prealloc'  : 'Wallet (lukewarm) - CoW Disabled',
}

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer', 
    '311.compression',
    '501.graph-pagerank',
    '502.graph-mst',
    '503.graph-bfs',
    '411.image-recognition'
]
palette = sns.color_palette("pastel", n_colors=len(VARIANTS*2))
hatches = ["", "//", "xx", "\\\\", ".."]
linestyles = ["-", "--", "-.", ":", "-"]

INVOCATION_LATENCY_PATH="output/invocation_latency_cow.csv"
INVOCATION_LATENCY_MEAN_PATH="output/invocation_latency_mean_cow.csv"

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
            else:
                print(f"[WARN] Result path {result_path} not found")
        
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
            else:
                print(f"[WARN] Result path {result_path} not found")
        
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
    wallet_variants = ['wallet', 'wallet_cow_prealloc']
    
    # Update labels for clarity
    custom_labels = {
        'wallet_cow_prealloc': 'Wallet (CoW enabled)',
        'wallet': 'Wallet (CoW disabled)'
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
    plt.savefig(output_dir / 'wallet_cow_invocation_latency_cdf_linear.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'wallet_cow_invocation_latency_cdf_linear.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / 'wallet_cow_invocation_latency_cdf_linear.pdf')
    
    plt.close()

def plot_wallet_comparison_stacked_bars(df, benchmarks, output_dir, geo_only=False):
    """Create stacked bar chart for wallet variants only"""
    wallet_variants = ['wallet', 'wallet_cow_prealloc']
    
    # Update labels for clarity
    custom_labels = {
        'wallet_cow_prealloc': 'Wallet (CoW enabled)',
        'wallet': 'Wallet (CoW disabled)'
    }
    
    # Filter data for just these wallet variants
    wallet_df = df[df['variant'].isin(wallet_variants)]
    
    # Set up the color palette for just these two variants
    wallet_palette = palette
    
    # Create plots for each execution type
    for exec_type in ['cold', 'hot']:
        figw = figwidth
        if geo_only:
            figw = 3.3/2
        fig, ax = plt.subplots(figsize=(figw, figheight))
        
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

        if geo_only:
            all_benchmarks = ['geomean']
        
        # Calculate bar positions
        n_variants = len(wallet_variants)
        width = 0.20  # Width of each bar
        variant_positions = np.arange(len(all_benchmarks))
        
        # Plot bars for each variant
        for i, variant in enumerate(wallet_variants):
            variant_data = filtered_df[filtered_df['variant'] == variant]
            # Prepare data including geomean
            values = []
            if not geo_only:
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
        ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
        plt.yticks(fontsize=TICKS_FONTSIZE)
        ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
        ax.set_xticks(variant_positions)
        if geo_only:
            xlabels = ['Geo. Mean']
            rotation = 0
            ax.set_ylim(0.1, 10)
        else:
            xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
            rotation = 15
        ax.set_xticklabels(xlabels, rotation=rotation, fontsize=TICKS_FONTSIZE)
        
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

        suffix = "_geomean" if geo_only else ""
        
        # Save plot (linear scale)
        plt.savefig(output_dir / f'wallet_cow_client_time_{exec_type}{suffix}.pdf', format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(output_dir / f'wallet_cow_client_time_{exec_type}{suffix}.png', format='png', dpi=300, bbox_inches='tight')
        crop_pdf(output_dir / f'wallet_cow_client_time_{exec_type}{suffix}.pdf')
        
        plt.close()

def plot_wallet_comparison_grouped_bars(df, benchmarks, output_dir, geo_only=False):
    """Create grouped bar charts for wallet variants, including a log-scale version."""
    
    wallet_variants = ['wallet', 'wallet_cow_prealloc']
    exec_types = ['cold', 'hot']
    
    # Define labels and order
    custom_labels = {
        #'wallet': 'CoW Disabled',
        #'wallet_cow_prealloc': 'CoW Enabled'
        'wallet': '(w/o CoW)',
        'wallet_cow_prealloc': '(w/ CoW)'
    }
    colors_group = [None] * len(VARIANTS*2)
    colors_group[0] = palette[0]
    colors_group[1] = palette[0]
    colors_group[2] = palette[1]
    colors_group[3] = palette[1]
    hatches_group = ['', '//', '', '//']
    
    # Filter only the relevant data
    wallet_df = df[df['variant'].isin(wallet_variants)]

    figw = figwidth
    if geo_only:
        figw = 3.3/2
    fig, ax = plt.subplots(figsize=(figw, figheight))
  
    # Benchmarks + Geometric Mean
    all_benchmarks = benchmarks + ['geomean']

    if geo_only:
        all_benchmarks = ['geomean']
    
    # Bar positions and widths
    n_variants = len(wallet_variants) * len(exec_types)  # 4 bars per benchmark
    width = 0.15  # Bar width
    positions = np.arange(len(all_benchmarks))  # X positions
    
    bar_positions = []
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
            if geo_only:
                values = [geomean]
            else:
                values.append(geomean)
            
            # Plot bars
            #label = f"{exec_type.capitalize()} - {custom_labels[variant]}"
            label = f"{exec_type.capitalize()} {custom_labels[variant]}"
            ax.bar(positions + offset, values, width, label=label, color=colors_group[i*2], hatch=hatches_group[j], edgecolor='black')
            
            bar_positions.append(positions + offset)
    
    # Customize plot
    ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
    ax.set_xticks(positions)
    if geo_only:
        xlabels = ['Geo. Mean']
        rotation = 0
        ax.set_ylim(0.1, 10)
    else:
        xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
        rotation = 15
    ax.set_xticklabels(xlabels, rotation=rotation, fontsize=TICKS_FONTSIZE)
    
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Legend
    ax.legend(loc='upper right', fontsize=LEGEND_FONTSIZE)
    
    # Grid and formatting
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.set_ylim(bottom=0)

    suffix = "_geomean" if geo_only else ""
    
    # Save linear-scale plot
    output_dir = Path(output_dir)
    plt.tight_layout()
    plt.savefig(output_dir / f'wallet_cow_client_time_grouped{suffix}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'wallet_cow_client_time_grouped{suffix}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'wallet_cow_client_time_grouped{suffix}.pdf')
    
    # Create log-scale version
    fig_log, ax_log = plt.subplots(figsize=(figwidth, figheight))
    
    color_idx = 0
    # Iterate through variants in the same order as for the linear plot
    for j, exec_type in enumerate(exec_types):  # cold, hot
        for i, variant in enumerate(wallet_variants):  # CoW Disabled, CoW Enabled           
            # Get the data
            variant_exec_df = wallet_df[(wallet_df['variant'] == variant) & (wallet_df['type'] == exec_type)]
            values = []
            for bench in benchmarks:
                bench_data = variant_exec_df[variant_exec_df['benchmark'] == bench]
                values.append(bench_data['client_time'].values[0] if not bench_data.empty else np.nan)
                
            # Compute geomean the same way
            geomean = np.exp(np.mean(np.log(values))) if np.all(np.array(values) > 0) else np.nan
            if geo_only:
                values = [geomean]
            else:
                values.append(geomean)
            
            # Calculate positions with the same offset as in the linear plot
            offset = ((j * len(wallet_variants) + i) - n_variants / 2 + 0.5) * width
            
            # Plot bars
            label = f"{exec_type.capitalize()} - {custom_labels[variant]}"
            ax_log.bar(positions + offset, values, width, label=label, 
                      color=colors_group[color_idx], hatch=hatches_group[color_idx], edgecolor='black')
            color_idx+=1
        
    ax_log.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
    ax_log.set_xticks(positions)
    ax_log.set_xticklabels(xlabels, rotation=rotation, fontsize=TICKS_FONTSIZE)
    
    ax_log.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    ax_log.set_yscale('log')
    ax_log.yaxis.grid(True, linestyle='--', alpha=0.7)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    
    ax_log.legend(loc='upper right', fontsize=LEGEND_FONTSIZE)
    
    # Save log-scale plot
    plt.tight_layout()
    plt.savefig(output_dir / f'wallet_cow_client_time_grouped_log{suffix}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'wallet_cow_client_time_grouped_log{suffix}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'wallet_cow_client_time_grouped_log{suffix}.pdf')
    
    plt.close(fig)
    plt.close(fig_log)

def print_performance_summary(df, benchmarks):
    """Print geometric mean values and performance improvements."""
    #wallet_variants = ['wallet', 'wallet_cow_prealloc']
    wallet_variants = ['wallet_cow_prealloc', 'wallet_no_cow_prealloc', 'wallet_warm_cow_prealloc']
    exec_types = ['cold', 'hot']
    
    # Filter data for wallet variants
    wallet_df = df[df['variant'].isin(wallet_variants)]
    
    print("\n===== PERFORMANCE SUMMARY =====")
    print("Geometric Mean Client Times (seconds):")
    
    improvements = {}
    
    for exec_type in exec_types:
        print(f"\n{exec_type.capitalize()} Start:")
        
        geomeans = {}
        for variant in wallet_variants:
            variant_data = wallet_df[(wallet_df['variant'] == variant) & (wallet_df['type'] == exec_type)]
            values = variant_data['client_time'].values
            
            # Calculate geometric mean (using log and exp to avoid numerical issues)
            if len(values) > 0 and np.all(values > 0):
                geomean = np.exp(np.mean(np.log(values)))
                geomeans[variant] = geomean
                variant_label = "With CoW" if variant == 'wallet_cow_prealloc' else "Without CoW"
                print(f"  {variant_label}: {geomean:.4f}s")
            else:
                print(f"  {variant}: No valid data")
                geomeans[variant] = np.nan
        
        # Calculate improvement
        if 'wallet_no_cow_prealloc' in geomeans and 'wallet_cow_prealloc' in geomeans:
            if not np.isnan(geomeans['wallet_no_cow_prealloc']) and not np.isnan(geomeans['wallet_cow_prealloc']):
                improvement = ((geomeans['wallet_no_cow_prealloc'] - geomeans['wallet_cow_prealloc']) / geomeans['wallet_no_cow_prealloc']) * 100
                improvements[exec_type] = improvement
                print(f"  Improvement with CoW: {improvement:.2f}%")
            else:
                print("  Improvement: Cannot calculate (missing data)")
        else:
            print("  Improvement: Cannot calculate (missing variants)")
    
    # Per-benchmark performance improvements
    print("\n\nPer-Benchmark Performance Improvements:")
    
    for exec_type in exec_types:
        print(f"\n{exec_type.capitalize()} Start:")
        
        for bench in benchmarks:
            without_cow_data = wallet_df[(wallet_df['variant'] == 'wallet_no_cow_prealloc') & 
                                        (wallet_df['type'] == exec_type) & 
                                        (wallet_df['benchmark'] == bench)]
            with_cow_data = wallet_df[(wallet_df['variant'] == 'wallet_cow_prealloc') & 
                                     (wallet_df['type'] == exec_type) & 
                                     (wallet_df['benchmark'] == bench)]
            
            if not without_cow_data.empty and not with_cow_data.empty:
                without_cow_time = without_cow_data['client_time'].values[0]
                with_cow_time = with_cow_data['client_time'].values[0]
                
                if without_cow_time > 0:  # Avoid division by zero
                    bench_improvement = ((without_cow_time - with_cow_time) / without_cow_time) * 100
                    bench_name = bench.split('.')[1]  # Extract readable name from benchmark ID
                    print(f"  {bench_name}: {without_cow_time:.4f}s → {with_cow_time:.4f}s (Improvement: {bench_improvement:.2f}%)")
                else:
                    print(f"  {bench}: Cannot calculate (zero or negative time)")
            else:
                print(f"  {bench}: Missing data")
    
    print("\n================================")
    
    # Add the formatted table
    print("\n\nPerformance Comparison Table:")
    print("Benchmark                 Cold (w/o) Cold (w/)  Cold Impr. Hot (w/o)  Hot (w/)   Hot Impr. ")
    print("--------------------------------------------------------------------------------")
    
    # Collect data for all benchmarks
    benchmark_data = []
    cold_improvements = []
    hot_improvements = []
    
    for bench in benchmarks:
        bench_name = bench.split('.')[1]
        
        cold_without = wallet_df[(wallet_df['variant'] == 'wallet_no_cow_prealloc') & 
                                (wallet_df['type'] == 'cold') & 
                                (wallet_df['benchmark'] == bench)]
        cold_with = wallet_df[(wallet_df['variant'] == 'wallet_cow_prealloc') & 
                            (wallet_df['type'] == 'cold') & 
                            (wallet_df['benchmark'] == bench)]
        
        hot_without = wallet_df[(wallet_df['variant'] == 'wallet_no_cow_prealloc') & 
                              (wallet_df['type'] == 'hot') & 
                              (wallet_df['benchmark'] == bench)]
        hot_with = wallet_df[(wallet_df['variant'] == 'wallet_cow_prealloc') & 
                           (wallet_df['type'] == 'hot') & 
                           (wallet_df['benchmark'] == bench)]
        
        # Initialize values
        cold_wo_time = cold_w_time = hot_wo_time = hot_w_time = np.nan
        cold_impr = hot_impr = np.nan
        
        # Extract values if data exists
        if not cold_without.empty:
            cold_wo_time = cold_without['client_time'].values[0]
        if not cold_with.empty:
            cold_w_time = cold_with['client_time'].values[0]
        if not hot_without.empty:
            hot_wo_time = hot_without['client_time'].values[0]
        if not hot_with.empty:
            hot_w_time = hot_with['client_time'].values[0]
        
        # Calculate improvements
        if cold_wo_time > 0 and not np.isnan(cold_w_time):
            cold_impr = ((cold_wo_time - cold_w_time) / cold_wo_time) * 100
            cold_improvements.append(cold_impr)
        
        if hot_wo_time > 0 and not np.isnan(hot_w_time):
            hot_impr = ((hot_wo_time - hot_w_time) / hot_wo_time) * 100
            hot_improvements.append(hot_impr)
        
        benchmark_data.append({
            'name': bench_name,
            'cold_wo': cold_wo_time,
            'cold_w': cold_w_time,
            'cold_impr': cold_impr,
            'hot_wo': hot_wo_time,
            'hot_w': hot_w_time,
            'hot_impr': hot_impr
        })
    
    # Print each row
    for data in benchmark_data:
        name = data['name']
        cold_wo = f"{data['cold_wo']:.4f}s" if not np.isnan(data['cold_wo']) else "N/A"
        cold_w = f"{data['cold_w']:.4f}s" if not np.isnan(data['cold_w']) else "N/A"
        cold_impr = f"{data['cold_impr']:.2f}%" if not np.isnan(data['cold_impr']) else "N/A"
        hot_wo = f"{data['hot_wo']:.4f}s" if not np.isnan(data['hot_wo']) else "N/A"
        hot_w = f"{data['hot_w']:.4f}s" if not np.isnan(data['hot_w']) else "N/A"
        hot_impr = f"{data['hot_impr']:.2f}%" if not np.isnan(data['hot_impr']) else "N/A"
        
        print(f"{name:<25} {cold_wo:<10} {cold_w:<10} {cold_impr:<10} {hot_wo:<10} {hot_w:<10} {hot_impr:<10}")
    
    print("--------------------------------------------------------------------------------")
    
    # Calculate geometric means of improvements
    if len(cold_improvements) > 0:
        cold_geomean = np.exp(np.mean(np.log(np.array(cold_improvements)))) if np.all(np.array(cold_improvements) > 0) else np.nan
        cold_geomean_str = f"{cold_geomean:.2f}%" if not np.isnan(cold_geomean) else "N/A"
    else:
        cold_geomean_str = "N/A"
        
    if len(hot_improvements) > 0:
        hot_geomean = np.exp(np.mean(np.log(np.array(hot_improvements)))) if np.all(np.array(hot_improvements) > 0) else np.nan
        hot_geomean_str = f"{hot_geomean:.2f}%" if not np.isnan(hot_geomean) else "N/A"
    else:
        hot_geomean_str = "N/A"
    
    print(f"Geometric Mean{' '*41}{cold_geomean_str:<10} {' '*21}{hot_geomean_str:<10}")
    
    print("\n================================")
    return improvements


def calculate_execution_overhead(df, benchmarks, cow_variant, no_cow_variant):
    # wallet_variants = ['wallet_cow_prealloc', 'wallet_no_cow_prealloc', 'wallet_warm_cow_prealloc', 'wallet_warm_no_cow_prealloc']
    wallet_variants = [cow_variant, no_cow_variant]
    exec_types = ['cold', 'hot']
    
    # Filter data for wallet variants
    wallet_df = df[df['variant'].isin(wallet_variants)]
    
    overheads = {}
    
    for exec_type in exec_types:
        geomeans = {}
        for variant in wallet_variants:
            variant_data = wallet_df[(wallet_df['variant'] == variant) & 
                                    (wallet_df['type'] == exec_type)]
            values = variant_data['exec_time'].values

            print(f"  {variant}: {values}")
            
            if len(values) > 0 and np.all(values > 0):
                geomean = np.exp(np.mean(np.log(values)))
                geomeans[variant] = geomean
            else:
                geomeans[variant] = np.nan
        
        print(f"\n{exec_type.capitalize()} Start:")
        print(f"  CoW Disabled: {geomeans[no_cow_variant]:.4f}s")
        print(f"  CoW Enabled: {geomeans[cow_variant]:.4f}s")
        
        # Calculate overhead
        if no_cow_variant in geomeans and cow_variant in geomeans:
            if not np.isnan(geomeans[no_cow_variant]) and not np.isnan(geomeans[cow_variant]):
                overhead = ((geomeans[cow_variant] - geomeans[no_cow_variant]) / 
                          geomeans[no_cow_variant]) * 100
                overheads[exec_type] = overhead
                print(f"{exec_type.capitalize()} start overhead of CoW: {overhead:.2f}%")

    return overheads


def main():
    global VARIANTS

    # Add wallet variants with preallocation for comparison plots
    #VARIANTS = ['wallet', 'wallet_cow_prealloc']
    #VARIANTS = ['wallet_cow_prealloc', 'wallet_no_cow_prealloc', 'wallet_warm_cow_prealloc', 'wallet_warm_no_cow_prealloc']
    VARIANTS = ['wallet_cow_prealloc', 'wallet_no_cow_prealloc', 'wallet_warm_cow_prealloc']
    
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
    plot_wallet_comparison_stacked_bars(client_df, common_benchmarks, output_dir, geo_only=True)
    plot_wallet_comparison_grouped_bars(client_df, common_benchmarks, output_dir, geo_only=True)
    
    print("Wallet comparison plots saved in output directory")
    
    # Print performance summary
    print_performance_summary(client_df, common_benchmarks)

    print("\nCalculating execution overhead...")
    overheads = calculate_execution_overhead(client_df, common_benchmarks, "wallet_cow_prealloc", "wallet_no_cow_prealloc")
    #print("\nCalculating execution overhead (lukewarm)...")
    #overheads = calculate_execution_overhead(client_df, common_benchmarks, "wallet_warm_cow_prealloc", "wallet_warm_no_cow_prealloc")

if __name__ == "__main__":
    main()
