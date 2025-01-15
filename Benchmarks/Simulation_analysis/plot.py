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
TICKS_FONTSIZE = 7
LEGEND_FONTSIZE = 6
ANNOTATION_SIZE = 4
palette = sns.color_palette("deep", n_colors=6)

def format_nodes(value):
    """Format node sizes into math abbreviated format"""
    if value < 1024:
        return f"{value:.0f}"
    else:
        value /= 1024
        return f"{value:.0f}K"

def parse_simulation_results(file_path):
    """Parse the simulation results file into a structured format"""
    data = []
    current_variant = None
    current_entry = {}
    
    with open(file_path, 'r') as f:
        content = f.read()
        
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('**'):
            if current_variant and len(current_entry) == 5:
                data.append({
                    'variant': current_variant,
                    **current_entry
                })
            current_variant = line.strip('* ').strip()
            current_entry = {}
        elif current_variant:
            if line.startswith('Total simulation time:'):
                current_entry['simulation_time'] = float(line.split(':')[1].strip())
            elif line.startswith('Warm boot rate:'):
                current_entry['warm_boot_rate'] = float(line.split(':')[1].strip())
            elif line.strip().startswith('Avg:'):
                current_entry['avg_delay'] = float(line.split(':')[1].strip())
            elif line.startswith('num_nodes:'):
                current_entry['num_nodes'] = int(line.split(':')[1].strip())
            elif line.startswith('percentage_soft_warm:'):
                current_entry['percentage_soft_warm'] = float(line.split(':')[1].strip())
    
    if current_variant and len(current_entry) == 5:
        data.append({
            'variant': current_variant,
            **current_entry
        })
    
    return pd.DataFrame(data)

def create_scalability_plot(data, metric, output_dir, y_scale='linear'):
    """Create line plot for scalability analysis"""
    figwidth = 3.3
    figheight = 2.2
    
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
    # Define markers for different variants
    markers = ['o', 's', '^', 'D', 'v', 'p']
    
    # Get unique node values and create position mapping
    all_nodes = sorted(data['num_nodes'].unique())
    node_positions = {node: i for i, node in enumerate(all_nodes)}
    
    # Plot VM and CVM (percentage_soft_warm = 0)
    for i, variant in enumerate(['VM', 'CVM']):
        variant_data = data[
            (data['variant'] == variant) & 
            (data['percentage_soft_warm'] == 0)
        ]
        if not variant_data.empty:
            # Convert node values to positions
            x_positions = [node_positions[n] for n in variant_data['num_nodes']]
            ax.plot(x_positions, 
                   variant_data[metric],
                   label=variant,
                   color=palette[i],
                   marker=markers[i],
                   markersize=1,
                   linewidth=1)
    
    # Plot Wallet with different percentage_soft_warm values
    soft_warm_values = [0, 0.3, 0.6, 0.9]
    for i, soft_warm in enumerate(soft_warm_values):
        wallet_data = data[
            (data['variant'] == 'WALLET') & 
            (data['percentage_soft_warm'] == soft_warm)
        ]
        if not wallet_data.empty:
            # Convert node values to positions
            x_positions = [node_positions[n] for n in wallet_data['num_nodes']]
            label = f'Wallet ({soft_warm})'
            ax.plot(x_positions,
                   wallet_data[metric],
                   label=label,
                   color=palette[i+2],
                   marker=markers[i+2],
                   markersize=0.8,
                   linewidth=0.8)
    
    # Customize the plot
    ax.set_yscale(y_scale)
    
    # Set x-ticks to show actual node values
    ax.set_xticks(list(node_positions.values()))
    ax.set_xticklabels([str(format_nodes(n)) for n in all_nodes], fontsize=TICKS_FONTSIZE)
    
    ax.set_xlabel('Number of nodes', fontsize=TICKS_FONTSIZE)
    ylabel = 'Time (s)' if metric == 'simulation_time' else 'Average function delay (ms)'
    ax.set_ylabel(ylabel, fontsize=TICKS_FONTSIZE)
    
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    legend = plt.legend(bbox_to_anchor=(0.68, 0.98),
                       loc='upper left',
                       borderaxespad=0.,
                       frameon=True,
                       fontsize=LEGEND_FONTSIZE)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Set y-axis to start at 0 for linear scale
    if y_scale == 'linear':
        ax.set_ylim(bottom=0)
        
    # Set x-axis limits with some padding
    ax.set_xlim(-0.2, len(all_nodes) - 0.8)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    metric_name = 'simulation_time' if metric == 'simulation_time' else 'function_delay'
    plt.savefig(output_dir / f'scalability_{metric_name}_{y_scale}.pdf',
                format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'scalability_{metric_name}_{y_scale}.png',
                format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate scalability plots')
    parser.add_argument('input_file', type=str, help='Path to the input file')
    parser.add_argument('--output-dir', type=str, default='output',
                       help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    data = parse_simulation_results(args.input_file)
    
    # Create plots for both metrics and scales
    metrics = ['simulation_time', 'avg_delay']
    for metric in metrics:
        create_scalability_plot(data, metric, args.output_dir, 'linear')
        create_scalability_plot(data, metric, args.output_dir, 'log')
    
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()