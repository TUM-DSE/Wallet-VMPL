#!/usr/bin/env python3

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import sys

# Import centralized plotting configuration
import sys
sys.path.append('../')
from motivation_plotting_config import *

LABEL_MAPPINGS_IPC_CHAIN = {
    'vm'                : 'VM',
    'kata'              : 'Containers',
    'cvm'               : 'CVM',
    'wallet'            : 'Wallet',
}

def format_bytes(size):
    """Format byte sizes with appropriate units"""
    for unit in ['B', 'KB', 'MB']:
        if size < 1024.0:
            return f"{size:.0f} {unit}"
        size /= 1024.0
    return f"{size:.0f} GB"

def load_csv_data(file_path):
    """Load and parse the CSV file with function chaining measurements"""
    try:
        df = pd.read_csv(file_path)
        return df
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        sys.exit(1)

def calculate_statistics(df):
    """Calculate mean and standard deviation for each variant and chain length"""
    stats = df.groupby(['variant', 'chain_length'])['time_taken'].agg(['mean', 'std']).reset_index()
    # If any std values are NaN (only one measurement), replace with 0
    stats['std'] = stats['std'].fillna(0)
    return stats

def create_bar_plot(stats, output_dir, y_scale='linear', group_width=0.8, bar_width_ratio=0.9):
    """Create a bar plot with error bars for function chaining performance
    
    Args:
        stats: DataFrame with statistics
        output_dir: Directory to save the plots
        y_scale: Scale for y-axis ('linear' or 'log')
        group_width: Width allocated for each group of bars (0-1)
        bar_width_ratio: Ratio of bar width to available space (0-1)
    """
    # Get unique variants and chain lengths
    variants = stats['variant'].unique()
    chain_lengths = sorted(stats['chain_length'].unique())
    
    # Create standardized plot
    fig, ax = create_standardized_plot(ax_height = 0.85, top_margin = 0.1, bottom_margin = 0.2)
    
    # Set up the bar width and positions
    # Calculate bar width based on group_width and bar_width_ratio
    bar_width = (group_width / len(variants)) * bar_width_ratio
    
    # Use equally spaced positions for x-ticks
    x_positions_groups = list(range(1, len(chain_lengths) + 1))
    
    # Plot bars for each variant
    for i, variant in enumerate(variants):
        variant_data = stats[stats['variant'] == variant]
        
        # Process the data for this variant
        x_positions = []
        means = []
        stds = []
        
        for j, chain_length in enumerate(chain_lengths):
            chain_data = variant_data[variant_data['chain_length'] == chain_length]
            if not chain_data.empty:
                # Calculate position for this bar (using normalized positions)
                position = x_positions_groups[j] + (i - len(variants)/2 + 0.5) * bar_width
                x_positions.append(position)
                means.append(chain_data['mean'].values[0] * 1000)  # Convert seconds to milliseconds
                stds.append(chain_data['std'].values[0] * 1000)    # Convert seconds to milliseconds
        
        # Plot the bars with error bars
        bars = ax.bar(x_positions, means, bar_width, yerr=stds, 
               label=LABEL_MAPPINGS_IPC_CHAIN.get(variant, variant.capitalize()),
               color=PALETTE_PASTEL[i % len(PALETTE_PASTEL)],
               hatch=HATCHES[i % len(HATCHES)],
               edgecolor='black', linewidth=0,
               capsize=ERROR_BAR_CAP_SIZE, error_kw={'elinewidth': ERROR_BAR_LINE_WIDTH})
        
        # Add annotations for wallet variant
        if variant == 'wallet':
            for bar, value, pos in zip(bars, means, x_positions):
                # Format the value - different precision for small vs large values
                if value < 10:
                    formatted_value = f"{value:.2f}"
                else:
                    formatted_value = f"{value:.1f}"
                
                # Position the text above the bar
                y_pos = bar.get_height() + (stds[x_positions.index(pos)] * 0.5) + 3
                ax.text(pos+0.07, y_pos, formatted_value, ha='center', va='bottom', 
                        fontsize=ANNOTATION_SIZE, rotation=0)

    # Apply consistent styling
    apply_consistent_style(ax, 
                        title=f"Communication latency ({LOWER_BETTER_TITLE})",
                        xlabel="Function chain length",
                        ylabel="Time (ms)")
    
    # Customize the plot
    ax.set_yscale(y_scale)
    
    # Set x-ticks at equally spaced positions
    x_positions_groups = list(range(1, len(chain_lengths) + 1))
    ax.set_xticks(x_positions_groups)
    ax.set_xticklabels([str(length) for length in chain_lengths], fontsize=TICKS_FONTSIZE)
    
    # Set y-axis to start at 0 for linear scale
    if y_scale == 'linear':
        ax.set_ylim(bottom=0)
    
    # Set reasonable x-axis limits for equally spaced groups
    ax.set_xlim(0.5, len(chain_lengths) + 0.5)
    
    # Position legend at the top center
    legend = ax.legend(loc='center', bbox_to_anchor=(0.35, 0.8),
                     borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, 
                     ncols=2, columnspacing=0.3, labelspacing=0.2, 
                     borderpad=0.3, handletextpad=0.3)
    legend.get_frame().set_edgecolor('black')
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'IPC_chain_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'IPC_chain_{y_scale}.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate bar plots from function chaining data')
    parser.add_argument('input_file', type=str, nargs='?', default='chain_result.csv', help='Path to the input CSV file (default: chain_result.csv)')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory (default: output)')
    parser.add_argument('--group-width', type=float, default=0.8, help='Width allocated for each group of bars (0-1, default: 0.8)')
    parser.add_argument('--bar-width-ratio', type=float, default=0.9, help='Ratio of bar width to available space (0-1, default: 0.9)')
    
    args = parser.parse_args()
    
    # Load and process data
    df = load_csv_data(args.input_file)
    stats = calculate_statistics(df)
    
    # Create plots with linear and log scales
    create_bar_plot(stats, args.output_dir, y_scale='linear', 
                    group_width=args.group_width, bar_width_ratio=args.bar_width_ratio)
    create_bar_plot(stats, args.output_dir, y_scale='log',
                    group_width=args.group_width, bar_width_ratio=args.bar_width_ratio)
    
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()