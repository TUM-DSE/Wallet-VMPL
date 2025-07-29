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
#figheight = 2.0
figheight = 1.8
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
    '504.dna-visualisation',
    '411.image-recognition',
]
palette = sns.color_palette("pastel", n_colors=len(VARIANTS))
hatches = ["", "//", "xx", "\\\\", ".."]
linestyles = ["-", "--", "-.", ":", "-"]

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

def create_wallet_combined_plot(df, benchmarks, metric, output_dir, y_scale='linear', geo_only=False):
    """Create grouped bar chart with all four wallet variants in a single plot"""
    figw = figwidth
    figh = figheight
    if geo_only:
        figw = 3.3/2
        figh = 2.0
    fig, ax = plt.subplots(figsize=(figw, figh))
    
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
    
    # Calculate performance improvements for geo means
    cold_improvement = (geomean_cold_no_prealloc - geomean_cold_prealloc) / geomean_cold_no_prealloc * 100 if not np.isnan(geomean_cold_no_prealloc) and not np.isnan(geomean_cold_prealloc) else np.nan
    hot_improvement = (geomean_hot_no_prealloc - geomean_hot_prealloc) / geomean_hot_no_prealloc * 100 if not np.isnan(geomean_hot_no_prealloc) and not np.isnan(geomean_hot_prealloc) else np.nan
    
    # Calculate per-benchmark improvements
    benchmark_improvements = {}
    for i, bench in enumerate(benchmarks):
        cold_no = cold_no_prealloc[cold_no_prealloc['benchmark'] == bench][metric].values[0] if len(cold_no_prealloc[cold_no_prealloc['benchmark'] == bench]) > 0 else np.nan
        cold_pre = cold_prealloc[cold_prealloc['benchmark'] == bench][metric].values[0] if len(cold_prealloc[cold_prealloc['benchmark'] == bench]) > 0 else np.nan
        hot_no = hot_no_prealloc[hot_no_prealloc['benchmark'] == bench][metric].values[0] if len(hot_no_prealloc[hot_no_prealloc['benchmark'] == bench]) > 0 else np.nan
        hot_pre = hot_prealloc[hot_prealloc['benchmark'] == bench][metric].values[0] if len(hot_prealloc[hot_prealloc['benchmark'] == bench]) > 0 else np.nan
        
        cold_bench_improvement = (cold_no - cold_pre) / cold_no * 100 if not np.isnan(cold_no) and not np.isnan(cold_pre) and cold_no > 0 else np.nan
        hot_bench_improvement = (hot_no - hot_pre) / hot_no * 100 if not np.isnan(hot_no) and not np.isnan(hot_pre) and hot_no > 0 else np.nan
        
        benchmark_improvements[bench] = {
            'cold_improvement': cold_bench_improvement,
            'hot_improvement': hot_bench_improvement,
            'cold_no_prealloc': cold_no,
            'cold_prealloc': cold_pre,
            'hot_no_prealloc': hot_no,
            'hot_prealloc': hot_pre
        }
    
    # Return the geometric means and improvements instead of printing them
    results = {
        'metric': metric,
        'cold_no_prealloc': geomean_cold_no_prealloc,
        'cold_prealloc': geomean_cold_prealloc,
        'hot_no_prealloc': geomean_hot_no_prealloc,
        'hot_prealloc': geomean_hot_prealloc,
        'cold_improvement': cold_improvement,
        'hot_improvement': hot_improvement,
        'benchmark_improvements': benchmark_improvements
    }
    
    # Add geomean data to display
    all_benchmarks = benchmarks + ['geomean']

    if geo_only:
        all_benchmarks = ['geomean']
    
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
    if geo_only:
        cold_no_prealloc_values = [geomean_cold_no_prealloc]
    else:
        cold_no_prealloc_values = list(cold_no_prealloc[metric].values)
        cold_no_prealloc_values.append(geomean_cold_no_prealloc)
    positions_cold_no = positions - width*1.5
    bars1 = ax.bar(positions_cold_no, cold_no_prealloc_values, width, 
                   #label='Cold start (w/o preallocation)',
                   label='Cold (w/o prealloc)',
                 color=cold_color, edgecolor='black', hatch=no_hatch)
    
    # Cold with prealloc
    if geo_only:
        cold_prealloc_values = [geomean_cold_prealloc]
    else:
        cold_prealloc_values = list(cold_prealloc[metric].values)
        cold_prealloc_values.append(geomean_cold_prealloc)
    positions_cold_yes = positions - width*0.5
    bars2 = ax.bar(positions_cold_yes, cold_prealloc_values, width, 
                   #label='Cold start (w/ preallocation)',
                   label='Cold (w/ prealloc)',
                 color=cold_color, edgecolor='black', hatch=yes_hatch)
    
    # Hot no prealloc
    if geo_only:
        hot_no_prealloc_values = [geomean_hot_no_prealloc]
    else:
        hot_no_prealloc_values = list(hot_no_prealloc[metric].values)
        hot_no_prealloc_values.append(geomean_hot_no_prealloc)
    positions_hot_no = positions + width*0.5
    bars3 = ax.bar(positions_hot_no, hot_no_prealloc_values, width, 
                   #label='Hot start (w/o preallocation)',
                   label='Hot (w/o prealloc)',
                 color=hot_color, edgecolor='black', hatch=no_hatch)
    
    # Hot with prealloc
    if geo_only:
        hot_prealloc_values = [geomean_hot_prealloc]
    else:
        hot_prealloc_values = list(hot_prealloc[metric].values)
        hot_prealloc_values.append(geomean_hot_prealloc)
    positions_hot_yes = positions + width*1.5
    bars4 = ax.bar(positions_hot_yes, hot_prealloc_values, width, 
                   # label='Hot start (w/ preallocation)',
                   label='Hot (w/ prealloc)',
                 color=hot_color, edgecolor='black', hatch=yes_hatch)

    if geo_only:
        # add value labels on top of bars
        for i, bar in enumerate(bars1):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{bar.get_height():.2f}",
                    ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
        for i, bar in enumerate(bars2):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{bar.get_height():.2f}",
                    ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
        for i, bar in enumerate(bars3):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{bar.get_height():.2f}",
                    ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
        for i, bar in enumerate(bars4):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{bar.get_height():.2f}",
                    ha='center', va='bottom', fontsize=ANNOTATION_SIZE)

    
    # Customize the plot
    ax.set_yscale(y_scale)
    ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    ax.set_xticks(positions)
    if geo_only:
        #xlabels = ['Geo. Mean']
        xlabels = ['Geo. Mean']
        rotation = 0
        ax.set_ylim(0.1, 10)
        legend_loc = 'upper right'
        bbox_to_anchor=(0.98, 0.99)
    else:
        xlabels = [benchmark.split('.')[1] for benchmark in benchmarks] + ['Geo. Mean']
        rotation = 15
        legend_loc = 'upper left'
        bbox_to_anchor=(0.01, 0.98)
    ax.set_xticklabels(xlabels, rotation=rotation, fontsize=TICKS_FONTSIZE)
    
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    legend = plt.legend(bbox_to_anchor=bbox_to_anchor, loc=legend_loc,
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

    suffix = '_geomean' if geo_only else ''
    
    plt.savefig(output_dir / f'wallet_prealloc_{metric}_{y_scale}{suffix}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'wallet_prealloc_{metric}_{y_scale}{suffix}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'wallet_prealloc_{metric}_{y_scale}{suffix}.pdf')
    
    plt.close()
    
    return results

def create_improvement_plot(results, output_dir):
    """Create a bar plot showing the geometric mean of performance improvements"""
    # Filter for exec_time results only
    exec_time_results = next((r for r in results if r['metric'] == 'exec_time'), None)
    if not exec_time_results:
        print("Error: Could not find exec_time results")
        return
    
    # Calculate the geometric means from the benchmark improvements
    cold_improvements = []
    hot_improvements = []
    
    for bench, data in exec_time_results['benchmark_improvements'].items():
        if not np.isnan(data['cold_improvement']):
            cold_improvements.append(data['cold_improvement'])
        if not np.isnan(data['hot_improvement']):
            hot_improvements.append(data['hot_improvement'])
    
    geo_mean_cold_impr = np.exp(np.mean(np.log(np.abs(cold_improvements)))) if cold_improvements and np.all(np.array(cold_improvements) != 0) else np.nan
    geo_mean_hot_impr = np.exp(np.mean(np.log(np.abs(hot_improvements)))) if hot_improvements and np.all(np.array(hot_improvements) != 0) else np.nan
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(figwidth/2, figheight))
    
    # Define bar width and spacing
    bar_width = 0.25
    bar_spacing = 0.3  # Smaller spacing between bars (was default 1.0)
    
    # Define custom x positions for bars to place them closer together
    x_positions = [0, bar_width + bar_spacing]
    category_labels = ['Cold Start', 'Warm Start']
    improvements = [geo_mean_cold_impr, geo_mean_hot_impr]
    
    # Use different colors for bars
    colors = [palette[0], palette[1]]
    
    # Plot bars at custom positions
    bars = ax.bar(x_positions, improvements, color=colors, edgecolor='black', width=bar_width, linewidth=0)
    
    # Add value labels on top of bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                f'{height:.2f}%', ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
    
    # Set custom x-tick positions and labels
    ax.set_xticks(x_positions)
    ax.set_xticklabels(category_labels, fontsize=TICKS_FONTSIZE)
    
    # Customize the plot
    ax.set_ylabel('Performance Improvement (%)', fontsize=TICKS_FONTSIZE)
    ax.set_title('Higher is better ↑', fontsize=TITLE_FONTSIZE, color="navy")
    plt.yticks(fontsize=TICKS_FONTSIZE)
    
    # Set x-axis limits to center the bars and add left margin
    # Change from: ax.set_xlim(-bar_width/2, x_positions[-1] + bar_width)
    ax.set_xlim(-bar_width, x_positions[-1] + bar_width)
    
    # Add gridlines
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    # Set y-axis limit to start from 0
    ax.set_ylim(bottom=0)
    
    # Add more space at the top
    ylim = ax.get_ylim()
    ax.set_ylim(bottom=0, top=ylim[1] * 1.1)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save the plot
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'prealloc_performance_improvement_geomean.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'prealloc_performance_improvement_geomean.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / 'prealloc_performance_improvement_geomean.pdf')
    
    plt.close()

def main():
    global VARIANTS
    # Load and process the wallet cow variants only
    VARIANTS = ['wallet_cow_prealloc', 'wallet_cow_no_prealloc']
    df, common_benchmarks = load_and_process_data()
    
    # Create separate plots for each metric and execution type
    metrics = ['exec_time', 'client_time']
    
    # Collection to store all results
    all_results = []
    
    # Create new combined plots with all four wallet variants
    for metric in metrics:
        results_linear = create_wallet_combined_plot(df, common_benchmarks, metric, 'output', 'linear')
        results_log = create_wallet_combined_plot(df, common_benchmarks, metric, 'output', 'log')
        results_linear_geo = create_wallet_combined_plot(df, common_benchmarks, metric, 'output', 'linear', geo_only=True)
        results_log_geo = create_wallet_combined_plot(df, common_benchmarks, metric, 'output', 'log', geo_only=True)
        
        # Only add one result per metric (they all have the same geometric means)
        all_results.append(results_linear)
    
    # Create the improvement geometric mean plot
    create_improvement_plot(all_results, 'output')
    
    # Print all geometric means and improvements at the end
    print("\n======= PERFORMANCE SUMMARY =======")
    for result in all_results:
        metric = result['metric']
        print(f"\n--- Geometric Means for {metric} ---")
        print(f"Cold start (w/o prealloc): {result['cold_no_prealloc']:.4f}s")
        print(f"Cold start (w/ prealloc): {result['cold_prealloc']:.4f}s")
        print(f"Hot start (w/o prealloc): {result['hot_no_prealloc']:.4f}s")
        print(f"Hot start (w/ prealloc): {result['hot_prealloc']:.4f}s")
        
        # Print performance improvements
        if not np.isnan(result['cold_improvement']):
            print(f"Cold start improvement with preallocation: {result['cold_improvement']:.2f}%")
        
        if not np.isnan(result['hot_improvement']):
            print(f"Hot start improvement with preallocation: {result['hot_improvement']:.2f}%")
        
        # Print per-benchmark improvements
        print(f"\n--- Per-Benchmark Improvements for {metric} ---")
        print(f"{'Benchmark':<25} {'Cold (w/o)':<10} {'Cold (w/)':<10} {'Cold Impr.':<10} {'Hot (w/o)':<10} {'Hot (w/)':<10} {'Hot Impr.':<10}")
        print("-" * 80)
        
        # Collect improvement values for geometric mean calculation
        cold_improvements = []
        hot_improvements = []
        
        for bench, data in result['benchmark_improvements'].items():
            bench_name = bench.split('.')[1]
            cold_no = f"{data['cold_no_prealloc']:.4f}s" if not np.isnan(data['cold_no_prealloc']) else "N/A"
            cold_pre = f"{data['cold_prealloc']:.4f}s" if not np.isnan(data['cold_prealloc']) else "N/A"
            hot_no = f"{data['hot_no_prealloc']:.4f}s" if not np.isnan(data['hot_no_prealloc']) else "N/A"
            hot_pre = f"{data['hot_prealloc']:.4f}s" if not np.isnan(data['hot_prealloc']) else "N/A"
            
            cold_impr = f"{data['cold_improvement']:.2f}%" if not np.isnan(data['cold_improvement']) else "N/A"
            hot_impr = f"{data['hot_improvement']:.2f}%" if not np.isnan(data['hot_improvement']) else "N/A"
            
            print(f"{bench_name:<25} {cold_no:<10} {cold_pre:<10} {cold_impr:<10} {hot_no:<10} {hot_pre:<10} {hot_impr:<10}")
            
            # Collect non-NaN improvement values for geometric mean
            if not np.isnan(data['cold_improvement']):
                cold_improvements.append(data['cold_improvement'])
            if not np.isnan(data['hot_improvement']):
                hot_improvements.append(data['hot_improvement'])
        
        # Calculate geometric means of improvements
        geo_mean_cold_impr = np.exp(np.mean(np.log(np.abs(cold_improvements)))) if cold_improvements and np.all(np.array(cold_improvements) != 0) else np.nan
        geo_mean_hot_impr = np.exp(np.mean(np.log(np.abs(hot_improvements)))) if hot_improvements and np.all(np.array(hot_improvements) != 0) else np.nan
        
        # Print the geometric mean row
        print("-" * 80)
        geo_mean_cold_str = f"{geo_mean_cold_impr:.2f}%" if not np.isnan(geo_mean_cold_impr) else "N/A"
        geo_mean_hot_str = f"{geo_mean_hot_impr:.2f}%" if not np.isnan(geo_mean_hot_impr) else "N/A"
        print(f"{'Geometric Mean':<25} {'':<10} {'':<10} {geo_mean_cold_str:<10} {'':<10} {'':<10} {geo_mean_hot_str:<10}")
    
    print("\nPlots saved in output directory")

if __name__ == "__main__":
    main()
