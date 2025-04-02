#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import re
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
palette = sns.color_palette("pastel")
hatches = ["", "//", "xx", "\\\\", ".."]

def crop_pdf(input_path):
    """Use pdfcrop to crop the PDF file."""
    try:
        subprocess.run(['pdfcrop', input_path, input_path], check=True)
        print(f"Successfully cropped {input_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error cropping PDF {input_path}: {e}")
    except FileNotFoundError:
        print("pdfcrop command not found. Please install texlive-extra-utils package.")

motivation_categories = ['VM\n(KVM-Linux)', 'CVM\n(SEV-SNP)']

def load_data(file_path):
    """Parse the input file containing measurements"""
    with open(file_path, 'r') as f:
        content = f.read()

    # Split into sections
    sections = content.split('\n\n')
    data = {}
    
    for section in sections:
        if not section.strip():
            continue
        
        lines = section.strip().split('\n')
        section_name = lines[0].replace(':', '')
        measurements = {}
        
        for line in lines[1:]:
            if not line.strip():
                continue
            # Extract component and value
            component, values = line.split(':', 1)
            value_match = re.search(r'([\d.]+)\s*ms', values)
            if value_match:
                measurements[component.strip()] = float(value_match.group(1))
        
        data[section_name] = measurements
    
    return data

def calculate_categories(raw_data, type_="all", alloc=None, cow=None):
    """Calculate values for each category"""
    # BENCHMARKS = [
    # '110.dynamic-html', #'120.uploader',
    # '210.thumbnailer',
    # '311.compression',
    # '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    # '504.dna-visualisation'
    # ]
    # XXX: this is the order that other plot uses
    BENCHMARKS = [
    '210.thumbnailer',
    '502.graph-mst',
    '110.dynamic-html',
    '501.graph-pagerank',
    '504.dna-visualisation',
    '503.graph-bfs',
    '311.compression',
    ]
    
    # Filter by alloc and cow if specified
    filtered_data = raw_data
    if alloc is not None:
        filtered_data = filtered_data[filtered_data["alloc"] == alloc]
    if cow is not None:
        filtered_data = filtered_data[filtered_data["cow"] == cow]
    
    categories = {}
    for b in BENCHMARKS:
        df = filtered_data[filtered_data["benchmark"].str.contains(b)]
        if df.empty:  # Skip benchmarks with no data matching the filters
            continue
            
        name = b.split('.')[1] # remove the number
        if type_ == "all":
            categories[name] = {
                "Zygote Image Copy": df["zygote_data_copy"].mean() / 1e6,
                "Zygote Initilization": df["zygote_init"].mean() / 1e6 ,
                "Trustlet Creation": df["trustlet_creation"].mean() / 1e6,
                "Trustlet Add Function": df["trustlet_function"].mean() / 1e6,
                "Trustlet Creation": (df["trustlet_creation"].mean() + df["trustlet_function"].mean()) / 1e6,
                "Invoke Setup": (df["invoke_data"].mean() + df["invoke_setup"].mean()) / 1e6,
                "Invoke Data Copy": df["invoke_data_copy"].mean() / 1e6,
                "Invoke Result Copy": df["invoke_result_copy"].mean()/ 1e6,
            }
        elif type_ == "all_simple":
            categories[name] = {
                "Zygote creation": (df["zygote_init"].mean() + df["zygote_data_copy"].mean()) / 1e6,
                "Trustlet creation": (df["trustlet_function"].mean() + df["trustlet_creation"].mean()) / 1e6,
                "Input copy": df["invoke_data_copy"].mean() / 1e6,
                "Output copy": df["invoke_result_copy"].mean()/ 1e6,
            }
        elif type_ == "zygote":
            categories[name] = {
                "Zygote creation": (df["zygote_init"].mean() + df["zygote_data_copy"].mean()) / 1e6,
            }
        elif type_ == "zygote_full":
            categories[name] = {
                "Zygote Image Copy": df["zygote_data_copy"].mean() / 1e6,
                "Zygote Initilization": df["zygote_init"].mean() / 1e6 ,
            }
        elif type_ == "trustlet":
            categories[name] = {
                "Trustlet creation": (df["trustlet_function"].mean() + df["trustlet_creation"].mean()) / 1e6,
            }
        elif type_ == "trustlet_full":
            categories[name] = {
                "Trustlet creation": df["trustlet_creation"].mean() / 1e6,
                "Trustlet add function": df["trustlet_function"].mean() / 1e6,
            }
        elif type_ == "invoke":
            categories[name] = {
                "Trustlet creation": (df["trustlet_function"].mean() + df["trustlet_creation"].mean()) / 1e6,
                "Invoke setup": (df["invoke_data"].mean() + df["invoke_setup"].mean()) / 1e6,
                "Invoke Data Copy": df["invoke_data_copy"].mean() / 1e6,
                "Invoke Result Copy": df["invoke_result_copy"].mean()/ 1e6,
            }
        elif type_ == "datacopy":
            categories[name] = {
                "Invoke Data Copy": df["invoke_data_copy"].mean() / 1e6,
                "Invoke Result Copy": df["invoke_result_copy"].mean()/ 1e6,
            }
        elif type_ == "invoke_full":
            categories[name] = {
                "Trustlet Creation": df["trustlet_creation"].mean() / 1e6,
                "Trustlet Add Function": df["trustlet_function"].mean() / 1e6,
                "Invoke Data Copy": df["invoke_data"].mean() / 1e6,
                "Invoke Setup": df["invoke_setup"].mean() / 1e6,
                "Invoke Data Copy": df["invoke_data_copy"].mean() / 1e6,
                "Invoke Result Copy": df["invoke_result_copy"].mean()/ 1e6,
            }
        else:
            print(f"Invalid: {type_}")
            exit(1)
        print(categories)
    return categories

def create_cutoff_plot(categories, output_dir, y_scale='linear', suffix=''):
    """Create stacked bar chart with a broken y-axis for boot time data"""
    # Convert to DataFrame
    data = []
    for category, components in categories.items():
        row = {'Category': category}
        row.update(components)
        data.append(row)
    
    df = pd.DataFrame(data)
    df.set_index('Category', inplace=True)
    
    figwidth = 3.3  # 3.3 inch for single column, 7 inch for double column
    figheight = 2.2
    # Create the plot with increased size
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(figwidth, figheight))

    # Set y-axis limits with a break
    ax1.set_ylim(400, 18000)  # upper section for high values
    ax2.set_ylim(0, 90)        # lower section for most data
    
    # Hide the spines between ax1 and ax2
    ax1.spines.bottom.set_visible(False)
    ax2.spines.top.set_visible(False)

    # Hide the xaxis from the upper plot
    ax1.get_xaxis().set_visible(False)

    # Add break marks
    d = .5  # proportion of vertical to horizontal extent of the slanted line
    kwargs = dict(marker=[(-1, -d), (1, d)], markersize=TICKS_FONTSIZE,
                  linestyle="none", color='k', mec='k', mew=1, clip_on=False)
    ax1.plot([0, 1], [0, 0], transform=ax1.transAxes, **kwargs)
    ax2.plot([0, 1], [1, 1], transform=ax2.transAxes, **kwargs)

    # Plot stacked bars with wider bars
    df.plot(kind='bar', stacked=True, ax=ax1, color=palette, linewidth=0, edgecolor='black', width=0.8)
    df.plot(kind='bar', stacked=True, ax=ax2, color=palette, linewidth=0, edgecolor='black', width=0.8, legend=False)
    
    # Add hatches for better distinction
    bars1 = ax1.patches
    bars2 = ax2.patches
    n_bars = len(df)
    n_categories = len(df.columns)
    patterns = [h for h in hatches for _ in range(n_bars)]
    for bar, pattern in zip(bars1, patterns):
        bar.set_hatch(pattern)
    for bar, pattern in zip(bars2, patterns):
        bar.set_hatch(pattern)
    
    # Add value labels on the top bars
    for i, category in enumerate(df.index):
        total = 0
        for j, value in enumerate(df.loc[category]):
            if value > 0:  # Only show non-zero values
                total += value
        
        # Add total on top of each bar - choose the axis depending where the total is
        format_ = f'{total:.1f}'
        print(f"type: {type_}, total: {total}")
        if type_ == "trustlet":
            format_ = f'{total:.2f}'
        if total > 50:
            ax1.text(i, total, format_, ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
        else:
            ax2.text(i, total, format_, ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
    
    # Customize the plot
    # Tick size
    ax1.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax1.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    ax2.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax2.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    
    # Fix xticks rotation
    plt.xticks(rotation=25)
    
    # Add y-axis label in the middle
    ax2.annotate(
        'Time (ms)',
        xy=(-0.28, 25),
        xytext=(-43, 35),
        textcoords='offset points',
        rotation=90,
        va='center',
        fontsize=TICKS_FONTSIZE,
    )
  
    # x-axis label
    # ax2.set_xlabel('Variant', fontsize=TICKS_FONTSIZE)
    ax2.set_xlabel('', fontsize=TICKS_FONTSIZE)
    
    # Title in the upper plot
    ax1.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Insert legend in the top right position
    legend = ax1.legend(bbox_to_anchor=(0.03, 0.97), loc='upper left',
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines for better readability
    ax1.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax2.yaxis.grid(True, linestyle='--', alpha=0.7)
       
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    plt.subplots_adjust(wspace=0, hspace=0.03)

    # Save plots with suffix
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'boot_time_cutoff{suffix}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'boot_time_cutoff{suffix}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'boot_time_cutoff{suffix}.pdf')
    
    plt.close()

def create_plot(categories, output_dir, y_scale='linear', motivation=False, type_="all", suffix=''):
    """Create stacked bar chart"""
    
    if motivation:
        categories = {k: categories[k] for k in motivation_categories if k in categories}
        figwidth = 2.2  # 3.3 inch for single column, 7 inch for double column
        figheight = 1.5
    else:
        figwidth = 3.3 # 3.3 inch for single column, 7 inch for double column
        #figheight = 2.2
        figheight = 2.0

    # Convert to DataFrame
    data = []
    for category, components in categories.items():
        row = {'Category': category}
        row.update(components)
        data.append(row)

    df = pd.DataFrame(data)
    df.set_index('Category', inplace=True)
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Plot stacked bars with wider bars
    if motivation:
        df.plot(kind='bar', stacked=True, ax=ax, color='C0', edgecolor='C0', width=0.8, legend=False)
    else:
        df.plot(kind='bar', stacked=True, ax=ax, color=palette, linewidth = 0, edgecolor='black', width=0.6)
    
    # Add hatches for better distinction
    bars = ax.patches
    n_bars = len(df)
    n_categories = len(df.columns)
    patterns = [h for h in hatches for _ in range(n_bars)]
    for bar, pattern in zip(bars, patterns):
        bar.set_hatch(pattern)
    
    y_max = 0
    # Add value labels on the bars
    for i, category in enumerate(df.index):
        total = 0
        for j, value in enumerate(df.loc[category]):
            if value > 0:  # Only show non-zero values
                total += value
        # Add total on top
        ax.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
        if total > y_max:
            y_max = total
    
    # Customize the plot
    ax.set_yscale(y_scale)
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    ax.set_xlabel('', fontsize=TICKS_FONTSIZE)
    plt.xticks(fontsize=TICKS_FONTSIZE, rotation=25)
    # ax.set_title('Boot Time', pad=5, fontsize=TITLE_FONTSIZE)
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    if not motivation:
      if type_ == "invoke" or type_ == "datacopy":
        bbox_to_anchor = (0.01, 0.98)
        loc = 'upper left'
      else:
        bbox_to_anchor = (0.01, 0.02)
        loc = 'lower left'
      legend = plt.legend(bbox_to_anchor=bbox_to_anchor, loc=loc, 
                        borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, framealpha=0.5)
      legend.get_frame().set_edgecolor('black')

    # Increase the border a bit to fit the annotations
    if (y_scale == "linear"):
      ax.set_ylim(top=y_max + 0.1*y_max)
    else:
      #ax.set_ylim(top=2*y_max)
      ax.set_ylim([0, y_max*1.1])
    ax.tick_params(axis = 'y', which = 'both', labelsize = TICKS_FONTSIZE)

    
    # Add gridlines for better readability
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)

    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save plots with suffix
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plot_type = 'motivation_' if motivation else ''
    plt.savefig(output_dir / f'{plot_type}runtime_init_{y_scale}_{type_}{suffix}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'{plot_type}runtime_init_{y_scale}_{type_}{suffix}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'{plot_type}runtime_init_{y_scale}_{type_}{suffix}.pdf')
    
    plt.close()

def create_side_by_side_plot(categories, output_dir, suffix=''):
    """Create side-by-side bar chart with a broken y-axis for time data"""
    # Convert to DataFrame in the right format for grouped bar chart
    data = []
    components_to_show = ["Zygote creation", "Trustlet creation", "Input copy", "Output copy"]
    
    # Ensure each benchmark has all components
    for benchmark, components in categories.items():
        for component_name in components_to_show:
            value = components.get(component_name, 0)
            data.append({
                'Benchmark': benchmark,
                'Component': component_name,
                'Time (ms)': value
            })
    
    df = pd.DataFrame(data)
    
    # Create the plot with increased size
    figwidth = 3.3  # 3.3 inch for single column
    figheight = 2.0  # Increased height to accommodate three subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True, figsize=(figwidth, figheight))
    
    # Set y-axis limits with two breaks
    max_zygote = df[df['Component'] == "Zygote creation"]['Time (ms)'].max()
    ax1.set_ylim(250, max_zygote-150)  # Upper section for high values (Zygote)
    ax2.set_ylim(0.6, 250)                 # Middle section for medium values
    ax3.set_ylim(0, 0.6)                  # Lower section for small values
    
    # Hide the spines between axes
    ax1.spines.bottom.set_visible(False)
    ax2.spines.top.set_visible(False)
    ax2.spines.bottom.set_visible(False)
    ax3.spines.top.set_visible(False)
    
    # Hide the xaxis from the upper plots
    ax1.get_xaxis().set_visible(False)
    ax2.get_xaxis().set_visible(False)
    ax1.tick_params(bottom=False)
    ax2.tick_params(bottom=False)
    
    # Add break marks
    d = .5  # proportion of vertical to horizontal extent of the slanted line
    kwargs = dict(marker=[(-1, -d), (1, d)], markersize=TICKS_FONTSIZE,
                  linestyle="none", color='k', mec='k', mew=1, clip_on=False)
    ax1.plot([0, 1], [0, 0], transform=ax1.transAxes, **kwargs)
    ax2.plot([0, 1], [1, 1], transform=ax2.transAxes, **kwargs)
    ax2.plot([0, 1], [0, 0], transform=ax2.transAxes, **kwargs)
    ax3.plot([0, 1], [1, 1], transform=ax3.transAxes, **kwargs)
    
    # Define the benchmark order as requested
    benchmark_order = [
        "thumbnailer", 
        "graph-mst", 
        "dynamic-html", 
        "graph-pagerank", 
        "dna-visualisation", 
        "graph-bfs", 
        "compression"
    ]
    
    # Filter and order the benchmarks according to the specified sequence
    available_benchmarks = df['Benchmark'].unique()
    ordered_benchmarks = [b for b in benchmark_order if b in available_benchmarks]
    
    # Plot grouped bars
    x = np.arange(len(ordered_benchmarks))
    width = 0.2  # width of the bars
    
    # Define y-axis section boundaries
    top_min = 250
    middle_min = 0.6
    middle_max = 250
    bottom_max = 0.6
    
    for i, component in enumerate(components_to_show):
        component_data = df[df['Component'] == component]
        
        for j, benchmark in enumerate(ordered_benchmarks):
            value = component_data[component_data['Benchmark'] == benchmark]['Time (ms)'].values[0]
            
            # Calculate what portion of the value goes in each section
            top_value = max(0, value - top_min)
            middle_value = min(middle_max - middle_min, max(0, min(value, middle_max) - middle_min))
            bottom_value = min(bottom_max, max(0, min(value, bottom_max)))
            
            # Plot each portion in its respective subplot
            if top_value > 0:
                ax1.bar(x[j] + (i - 1.5) * width, top_value, width, 
                        label=component if j == 0 else "", 
                        color=palette[i], linewidth=0, edgecolor='black', hatch=hatches[i])
            
            if middle_value > 0:
                ax2.bar(x[j] + (i - 1.5) * width, middle_value, width, 
                        label=component if j == 0 and top_value == 0 else "", 
                        color=palette[i], linewidth=0, edgecolor='black', hatch=hatches[i])
            
            if bottom_value > 0:
                ax3.bar(x[j] + (i - 1.5) * width, bottom_value, width, 
                        label=component if j == 0 and top_value == 0 and middle_value == 0 else "", 
                        color=palette[i], linewidth=0, edgecolor='black', hatch=hatches[i])
    
    # Customize the plot
    ax3.set_xlabel('', fontsize=TICKS_FONTSIZE)
    ax3.set_xticks(x)
    ax3.set_xticklabels(ordered_benchmarks, rotation=25, fontsize=TICKS_FONTSIZE)
    
    # Add y-axis label in the middle
    fig.text(-0.01, 0.5, 'Time (ms)', va='center', rotation='vertical', fontsize=TICKS_FONTSIZE)
    
    # Title
    ax1.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Create a single legend for all three subplots
    handles, labels = [], []
    for ax in [ax1, ax2, ax3]:
        h, l = ax.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)
    
    # Create a dictionary mapping labels to handles
    by_label = dict(zip(labels, handles))
    
    # Create ordered lists based on the desired order
    ordered_labels = [label for label in components_to_show if label in by_label]
    ordered_handles = [by_label[label] for label in ordered_labels]
    
    # Create the legend with the ordered items
    legend = ax1.legend(ordered_handles, ordered_labels, 
                      bbox_to_anchor=(0.01, 0.65), loc='upper left',
                      #bbox_to_anchor=(0.01, 0.90), loc='upper left',
                      borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, ncol=2)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines for better readability
    ax1.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax2.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax3.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    # Tick sizes
    for ax in [ax1, ax2, ax3]:
        ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    
    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(wspace=0, hspace=0.05)
    
    # Save plots with suffix
    output_path = Path(output_dir) / f'runtime_init_linear_time{suffix}.pdf'
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(str(output_path).replace('.pdf', '.png'), format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_path)
    
    plt.close()
    
    # Print summary of values for each component
    print(f"\n=== Summary of Component Values (ms) {suffix} ===")
    print(f"{'Benchmark':<20}", end="")
    for comp in components_to_show:
        print(f"{comp:<20}", end="")
    print()
    
    # Print dashes for formatting
    print("-" * (20 + 20 * len(components_to_show)))
    
    # Initialize sum for calculating averages
    component_sums = {comp: 0.0 for comp in components_to_show}
    
    # Print values for each benchmark
    for benchmark in ordered_benchmarks:
        print(f"{benchmark:<20}", end="")
        for comp in components_to_show:
            value = df[(df['Benchmark'] == benchmark) & (df['Component'] == comp)]['Time (ms)'].values[0]
            print(f"{value:<20.3f}", end="")
            component_sums[comp] += value
        print()
        
    # Print averages
    print("-" * (20 + 20 * len(components_to_show)))
    print(f"{'Average':<20}", end="")
    for comp in components_to_show:
        avg_value = component_sums[comp] / len(ordered_benchmarks)
        print(f"{avg_value:<20.3f}", end="")
    print()
    print("=" * (20 + 20 * len(components_to_show)))
    
    # Print total time for each benchmark
    print(f"\n=== Total Time per Benchmark (ms) {suffix} ===")
    for benchmark in ordered_benchmarks:
        total = 0
        for comp in components_to_show:
            total += df[(df['Benchmark'] == benchmark) & (df['Component'] == comp)]['Time (ms)'].values[0]
        print(f"{benchmark:<20}: {total:.3f}")
    
    total_avg = sum(component_sums.values()) / len(ordered_benchmarks)
    print("-" * 40)
    print(f"{'Average Total':<20}: {total_avg:.3f}")
    print("=" * 40)

def main():
    parser = argparse.ArgumentParser(description='Generate stacked bar charts from boot time data')
    parser.add_argument('input_file', type=str, help='Path to the input file')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    raw_data = pd.read_csv("results.csv")
    
    # Define combinations of alloc and cow to process
    combinations = [
        {"alloc": "prealloc", "cow": "cow", "suffix": "_prealloc_cow", "name": "Prealloc + CoW"},
        {"alloc": "prealloc", "cow": "no_cow", "suffix": "_prealloc_no_cow", "name": "Prealloc + No CoW"},
        {"alloc": "no_prealloc", "cow": "cow", "suffix": "_no_prealloc_cow", "name": "No Prealloc + CoW"},
        {"alloc": "no_prealloc", "cow": "no_cow", "suffix": "_no_prealloc_no_cow", "name": "No Prealloc + No CoW"},
        {"alloc": None, "cow": None, "suffix": "_all", "name": "All Configurations"}  # Process all data together
    ]
    
    # Dictionary to store summary data for all combinations
    all_summaries = {}
    
    # Process each combination
    for combo in combinations:
        alloc = combo["alloc"]
        cow = combo["cow"]
        suffix = combo["suffix"]
        name = combo["name"]
        print(f"\n\n=== Processing {alloc or 'all'} + {cow or 'all'} ===")
        
        # Store the all_simple categories for final summary
        all_simple_categories = None

        for type_ in ["all", "all_simple", "zygote", "trustlet", "invoke", "zygote_full",
                      "invoke_full", "datacopy"]:
            categories = calculate_categories(raw_data, type_=type_, alloc=alloc, cow=cow)
            
            # Skip if no data for this combination
            if not categories:
                continue
                
            # Store all_simple categories for final summary
            if type_ == "all_simple":
                all_simple_categories = categories
            
            # Create plots for all categories
            #create_cutoff_plot(categories, args.output_dir, suffix=suffix)
            create_plot(categories, args.output_dir, type_=type_, suffix=suffix)
            create_plot(categories, args.output_dir, 'log', type_=type_, suffix=suffix)
            
            # Create the side-by-side plot for all_simple
            if type_ == "all_simple":
                create_side_by_side_plot(categories, args.output_dir, suffix=suffix)

        # Print plots saved message
        print(f"Plots for {alloc or 'all'} + {cow or 'all'} saved in {args.output_dir}")
        
        # Collect summary data for this combination
        if all_simple_categories:
            components_to_show = ["Zygote creation", "Trustlet creation", "Input copy", "Output copy"]
            
            # Print the final summary table
            print(f"\n=== FINAL SUMMARY: {alloc or 'all'} + {cow or 'all'} ===")
            # Create and print summary table...
            data = []
            for benchmark, components in all_simple_categories.items():
                for component_name in components_to_show:
                    value = components.get(component_name, 0)
                    data.append({
                        'Benchmark': benchmark,
                        'Component': component_name,
                        'Time (ms)': value
                    })
            
            df = pd.DataFrame(data)
            
            # Define benchmark order
            benchmark_order = [
                "thumbnailer", 
                "graph-mst", 
                "dynamic-html", 
                "graph-pagerank", 
                "dna-visualisation", 
                "graph-bfs", 
                "compression"
            ]
            
            # Filter and order benchmarks
            available_benchmarks = df['Benchmark'].unique()
            ordered_benchmarks = [b for b in benchmark_order if b in available_benchmarks]
            
            # Print summary table
            print(f"\n=== FINAL SUMMARY: Component Values (ms) {suffix} ===")
            print(f"{'Benchmark':<20}", end="")
            for comp in components_to_show:
                print(f"{comp:<20}", end="")
            print()
            
            print("-" * (20 + 20 * len(components_to_show)))
            
            # Initialize component sums for averages
            component_sums = {comp: 0.0 for comp in components_to_show}
            benchmark_totals = {}
            
            # Print values for each benchmark
            for benchmark in ordered_benchmarks:
                print(f"{benchmark:<20}", end="")
                benchmark_total = 0
                for comp in components_to_show:
                    value = df[(df['Benchmark'] == benchmark) & (df['Component'] == comp)]['Time (ms)'].values[0]
                    print(f"{value:<20.3f}", end="")
                    component_sums[comp] += value
                    benchmark_total += value
                print()
                benchmark_totals[benchmark] = benchmark_total
            
            # Calculate average for each component
            component_avgs = {comp: component_sums[comp] / len(ordered_benchmarks) for comp in components_to_show}
            total_avg = sum(component_sums.values()) / len(ordered_benchmarks)
                
            # Print averages
            print("-" * (20 + 20 * len(components_to_show)))
            print(f"{'Average':<20}", end="")
            for comp in components_to_show:
                avg_value = component_sums[comp] / len(ordered_benchmarks)
                print(f"{avg_value:<20.3f}", end="")
            print()
            
            # Print total time for each benchmark
            print(f"\n=== FINAL SUMMARY: Total Time per Benchmark (ms) {suffix} ===")
            for benchmark in ordered_benchmarks:
                total = benchmark_totals[benchmark]
                print(f"{benchmark:<20}: {total:.3f}")
            
            print("-" * 40)
            print(f"{'Average Total':<20}: {total_avg:.3f}")
            print("=" * 40)
            
            # Store summary data for consolidated table
            all_summaries[name] = {
                'benchmarks': ordered_benchmarks,
                'component_avgs': component_avgs,
                'benchmark_totals': benchmark_totals,
                'total_avg': total_avg
            }
    
    # Print consolidated summary comparing all combinations
    print("\n\n" + "=" * 80)
    print(f"{'CONSOLIDATED SUMMARY OF ALL CONFIGURATIONS':^80}")
    print("=" * 80)
    
    # Assuming all combinations have the same benchmarks
    if all_summaries:
        # Get the list of benchmarks from the first summary (they should be the same for all)
        first_key = list(all_summaries.keys())[0]
        benchmarks = all_summaries[first_key]['benchmarks']
        components = ["Zygote creation", "Trustlet creation", "Input copy", "Output copy"]
        
        # Print average component times for each configuration
        print("\n--- Average Component Times (ms) ---\n")
        header = f"{'Component':<20}"
        for combo_name in all_summaries.keys():
            header += f"{combo_name:<20}"
        print(header)
        print("-" * (20 + 20 * len(all_summaries)))
        
        for component in components:
            row = f"{component:<20}"
            for combo_name, summary in all_summaries.items():
                row += f"{summary['component_avgs'][component]:<20.3f}"
            print(row)
        
        # Print total average for each configuration
        print("-" * (20 + 20 * len(all_summaries)))
        row = f"{'Total Average':<20}"
        for combo_name, summary in all_summaries.items():
            row += f"{summary['total_avg']:<20.3f}"
        print(row)
        
        # Print benchmark totals for each configuration
        print("\n--- Total Time per Benchmark (ms) ---\n")
        header = f"{'Benchmark':<20}"
        for combo_name in all_summaries.keys():
            header += f"{combo_name:<20}"
        print(header)
        print("-" * (20 + 20 * len(all_summaries)))
        
        for benchmark in benchmarks:
            row = f"{benchmark:<20}"
            for combo_name, summary in all_summaries.items():
                if benchmark in summary['benchmark_totals']:
                    row += f"{summary['benchmark_totals'][benchmark]:<20.3f}"
                else:
                    row += f"{'N/A':<20}"
            print(row)
        
        # Print average total again
        print("-" * (20 + 20 * len(all_summaries)))
        row = f"{'Average Total':<20}"
        for combo_name, summary in all_summaries.items():
            row += f"{summary['total_avg']:<20.3f}"
        print(row)
        
        print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
