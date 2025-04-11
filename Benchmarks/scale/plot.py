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
    """Parse the input CSV file containing function density measurements"""
    try:
        # Read the CSV file
        df = pd.read_csv(file_path)
        
        # Convert memory_usage from bytes to GB for easier visualization
        df['memory_usage_gb'] = df['memory_usage'] / (1024**3)
        
        # Group by variant and instances (number of functions)
        data = {}
        for variant, group in df.groupby('vm'):
            data[variant] = {
                'functions': group['instances'].tolist(),
                'memory': group['memory_usage_gb'].tolist()
            }
        
        return data
    except Exception as e:
        print(f"Error loading data: {e}")
        return {}

def create_line_plot(data, output_dir, y_scale='linear', motivation=False):
    """Create line plot for memory consumption based on number of functions"""
    # Create standardized plot
    fig, ax = create_standardized_plot(ax_height = 0.95, top_margin = 0.2, bottom_margin = 0.3)
    
    # Filter variants for motivation plot
    variants = list(data.keys())
    
    for i, variant in enumerate(variants):
        if variant in data:
            functions = data[variant]['functions']
            memory = data[variant]['memory']
            
            # Ensure data is sorted by number of functions
            sorted_data = sorted(zip(functions, memory))
            functions = [item[0] for item in sorted_data]
            memory = [item[1] for item in sorted_data]
            
            label = LABEL_MAPPINGS_VM.get(variant, variant)

            ax.plot(functions, memory, label=label,
                   color=PALETTE_REGULAR[i], marker='o', markersize=MARKER_SIZE,
                   linewidth=LINE_WIDTH)
            # Add annotation to the wallet variant
            if variant == 'wallet':
                # Annotate each data point for the wallet variant
                for j, (func, mem) in enumerate(zip(functions, memory)):
                    ax.annotate(f'{mem:.2f}',
                              xy=(func, mem),
                              xytext=(-4, -6),
                              textcoords='offset points',
                              fontsize=ANNOTATION_SIZE)
                              # arrowprops=dict(arrowstyle='->', color='black', connectionstyle='arc3'))
                    
    # Apply consistent styling
    apply_consistent_style(ax, 
                         title=LOWER_BETTER_TITLE,
                         xlabel="Number of Functions", 
                         ylabel="Memory Usage (GB)")
    
    # Customize the plot
    ax.set_yscale(y_scale)
    
    # Set reasonable x-axis ticks
    all_functions = []
    for variant in variants:
        if variant in data:
            all_functions.extend(data[variant]['functions'])
    
    unique_functions = sorted(set(all_functions))
    if len(unique_functions) <= 10:  # If we have a reasonable number of x-ticks
        ax.set_xticks(unique_functions)
    else:
        # Otherwise, create reasonable ticks
        if max(all_functions) > 100:
            step = 20
        elif max(all_functions) > 50:
            step = 10
        else:
            step = 5
        ax.set_xticks(range(0, max(all_functions) + step, step))
    
    # Set y-axis to start at 0 for linear scale
    if y_scale == 'linear':
        ax.set_ylim(bottom=-49)
    
    # Set reasonable x-axis limits
    ax.set_xlim(-50, max(all_functions) * 1.05)
    
    # Position legend at the top center
    legend = ax.legend(loc='center', bbox_to_anchor=(0.3, 0.7), framealpha=0.3,
                     borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, ncols=1)
    legend.get_frame().set_edgecolor('black')
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'function_density_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches=None)
    plt.savefig(output_dir / f'function_density_{y_scale}.png', format='png', dpi=300, bbox_inches=None)
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate line plots for function density')
    parser.add_argument('input_file', type=str, help='Path to the CSV input file')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    data = load_data(args.input_file)
    
    # Create plots for all variants
    create_line_plot(data, args.output_dir, 'linear')
    create_line_plot(data, args.output_dir, 'log')
    
    print(f"Function density plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()