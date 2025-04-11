#!/usr/bin/env python3

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import argparse
from pathlib import Path

# Import centralized plotting configuration
import sys
sys.path.append('..')
from motivation_plotting_config import *

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

def create_line_plot(data, output_dir, y_scale='linear'):
    """Create line plot with error bars"""
    message_sizes = [64.0, 256.0, 1024.0, 8192.0, 16384.0, 65536.0, 262144.0, 1048576.0]
    
    # Create standardized plot
    fig, ax = create_standardized_plot(ax_height = 0.7, bottom_margin= 0.45, top_margin=0.65)
    
    # Filter variants
    variants = ['Native', 'Gramine', 'Kata Containers', 'VM', 'CVM', 'Wallet']
    
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

            ax.errorbar(indices, means, yerr=stds, label=LABEL_MAPPINGS_SYSTEM[variant],
                       color=PALETTE_REGULAR[i], marker='o', markersize=MARKER_SIZE,
                       linewidth=LINE_WIDTH, capsize=ERROR_BAR_CAP_SIZE, capthick=ERROR_BAR_LINE_WIDTH,
                       elinewidth=ERROR_BAR_LINE_WIDTH)

    # Apply consistent styling
    apply_consistent_style(ax, 
                        title=LOWER_BETTER_TITLE,
                        xlabel="Message size",
                        ylabel="Time (ms)")
    
    # Fix xticks rotation
    plt.xticks(rotation=25)
    
    # Customize the plot
    ax.set_yscale(y_scale)
    
    # Set x-ticks at actual data points
    ax.set_xticks(range(1, len(message_sizes) + 1))
    labels = [format_bytes(size) for size in message_sizes]
    ax.set_xticklabels(labels, fontsize=TICKS_FONTSIZE)
    
    # Set y-axis to start at 0 for linear scale
    if y_scale == 'linear':
        ax.set_ylim(bottom=0)
    
    # Set reasonable x-axis limits
    ax.set_xlim(0.5, len(message_sizes) + 0.5)
    
    # Position legend at the top center
    legend = ax.legend(loc='center', bbox_to_anchor=(0.45, 1.5),
                     borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, ncols=2)
    legend.get_frame().set_edgecolor('black')
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'IPC_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches=None)
    plt.savefig(output_dir / f'IPC_{y_scale}.png', format='png', dpi=300, bbox_inches=None)
    
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
    
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()