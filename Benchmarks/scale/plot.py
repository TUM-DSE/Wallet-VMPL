#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import argparse
from pathlib import Path
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
palette = sns.color_palette("deep")

LABEL_MAPPINGS = {
    'vm'               : 'VM (KVM-Linux)',
    'kata'             : 'Containers (Kata)',
    'cvm'              : 'CVM (SEV-SNP)',
    'wallet'           : 'Wallet',
}

def crop_pdf(input_path):
    """Use pdfcrop to crop the PDF file."""
    try:
        subprocess.run(['pdfcrop', input_path, input_path], check=True)
        print(f"Successfully cropped {input_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error cropping PDF {input_path}: {e}")
    except FileNotFoundError:
        print("pdfcrop command not found. Please install texlive-extra-utils package.")

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
    figwidth = 3.3  # 3.3 inch for single column, 7 inch for double column
    figheight = 2.2
    
    fig, ax = plt.subplots(figsize=(figwidth, figheight))
    
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
            
            label = LABEL_MAPPINGS.get(variant, variant)
            ax.plot(functions, memory, label=label,
                   color=palette[i], marker='o', markersize=1.5,
                   linewidth=1)

    # Customize the plot
    ax.set_yscale(y_scale)
    
    # Set reasonable x-axis ticks
    # Try to use the actual function numbers from data if reasonable
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

    ax.set_xlabel('Number of Functions', fontsize=TICKS_FONTSIZE)
    ax.set_ylabel('Memory Usage (GB)', fontsize=TICKS_FONTSIZE)
    plt.xticks(fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)

    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    legend = plt.legend(bbox_to_anchor=(0.01, -0.3), loc='upper left',
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, ncols=3)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Set y-axis to start at 0 for linear scale
    if y_scale == 'linear':
        ax.set_ylim(bottom=0)
    
    # Set reasonable x-axis limits
    ax.set_xlim(0, max(all_functions) * 1.05)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'function_density_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'function_density_{y_scale}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'function_density_{y_scale}.pdf')
    
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