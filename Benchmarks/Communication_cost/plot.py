#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import argparse
from pathlib import Path

# Common graph settings
mpl.use("Agg")
mpl.rcParams["text.latex.preamble"] = r"\usepackage{amsmath}"
mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42
mpl.rcParams["font.family"] = "libertine"

sns.set_style("whitegrid")
sns.set_style("ticks", {"xtick.major.size": 8, "ytick.major.size": 8})
sns.set_context("paper", rc={"font.size": 5, "axes.titlesize": 5, "axes.labelsize": 8})

TITLE_FONTSIZE = 8
TICKS_FONTSIZE = 6
LEGEND_FONTSIZE = 6
ANNOTATION_SIZE = 4
palette = sns.color_palette("deep")

LABEL_MAPPINGS = {
    'Native'              : 'Native',
    'Gramine'             : 'LibOS (Gramine)',
    'VM'                  : 'VM (KVM-Linux)',
    'Kata Containers'     : 'Containers (Kata)',
    'CVM'                 : 'CVM (SEV-SNP)',
    'Wallet'              : 'Wallet',
}

def format_bytes(value):
    """Format byte sizes into human readable format"""
    for unit in ['B', 'KB', 'MB']:
        if value < 1024:
            return f"{value:.0f}{unit}"
        value /= 1024
    return f"{value:.0f}MB"

def load_data(file_path):
    """Parse the input file containing measurements"""
    data = {}
    current_section = None
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            if line.endswith(':'):
                current_section = line[:-1]
                data[current_section] = {'size': [], 'mean': [], 'std': []}
            elif line != 'size,mean,std':  # Skip header
                size, mean, std = map(float, line.split(','))
                data[current_section]['size'].append(size)
                data[current_section]['mean'].append(mean)
                data[current_section]['std'].append(std)
    
    return data

def create_line_plot(data, output_dir, y_scale='linear', motivation=False):
    """Create line plot with error bars"""
    if motivation:
        figwidth = 2.2  # 3.3 inch for single column, 7 inch for double column
        figheight = 1.5
        message_sizes = [64.0, 1024.0, 16384.0, 262144.0, 1048576.0]
    else:
        figwidth = 3.3  # 3.3 inch for single column, 7 inch for double column
        figheight = 2.2
        message_sizes = [64.0, 256.0, 1024.0, 8192.0, 16384.0, 65536.0, 262144.0, 1048576.0]
    
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    # Filter variants for motivation plot
    variants = ['VM', 'CVM'] if motivation else ['Native', 'Gramine', 'Kata Containers', 'VM', 'CVM', 'Wallet']
    
    # Collect all message sizes and create mapping to indices
    size_to_index = {size: i for i, size in enumerate(message_sizes, 1)}
    
    for i, variant in enumerate(variants):
        if variant in data:
            sizes = data[variant]['size']
            means = data[variant]['mean']
            stds = data[variant]['std']
            
            # Find matching indices for the chosen message_sizes
            matching_indices = [i for i, size in enumerate(sizes) if size in message_sizes]

            # Filter the data
            sizes = [sizes[i] for i in matching_indices]
            means = [means[i] for i in matching_indices]
            stds = [stds[i] for i in matching_indices]
            
            # Convert sizes to indices for plotting
            indices = [size_to_index[s] for s in sizes]
            
            ax.errorbar(indices, means, yerr=stds, label=LABEL_MAPPINGS[variant],
                       color=palette[i], marker='o', markersize=1.5,
                       linewidth=1, capsize=1, capthick=0.4,
                       elinewidth=0.4)
    
    # Customize the plot
    ax.set_yscale(y_scale)
    
    # Set x-ticks at actual data points with alternating labels
    ax.set_xticks(range(1, len(message_sizes) + 1))
    labels = [format_bytes(size) for size in message_sizes]
    ax.set_xticklabels(labels, fontsize=TICKS_FONTSIZE)

    ax.set_xlabel('Message size', fontsize=TICKS_FONTSIZE)
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)

    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    if motivation:
        legend = plt.legend(bbox_to_anchor=(0.32, 0.98), loc='upper right',
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    else:
        legend = plt.legend(bbox_to_anchor=(0.02, 0.93), loc='upper left',
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, framealpha=0.5)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Set y-axis to start at 0 for linear scale
    if y_scale == 'linear':
        ax.set_ylim(bottom=0)
    
    # Set reasonable x-axis limits
    ax.set_xlim(0.5, len(message_sizes) + 0.5)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plot_type = 'motivation_' if motivation else ''
    plt.savefig(output_dir / f'{plot_type}IPC_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'{plot_type}IPC_{y_scale}.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate line plots from IPC data')
    parser.add_argument('input_file', type=str, help='Path to the input file')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    data = load_data(args.input_file)
    
    # Create plots for all variants
    create_line_plot(data, args.output_dir, 'linear')
    create_line_plot(data, args.output_dir, 'log')
    
    # Create plots for VM and CVM only (motivation)
    create_line_plot(data, args.output_dir, 'linear', motivation=True)
    create_line_plot(data, args.output_dir, 'log', motivation=True)
    
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()
