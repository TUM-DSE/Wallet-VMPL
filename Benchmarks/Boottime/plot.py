#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import re

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
figwidth = 3.3 # 3.3 inch for single column, 7 inch for double column
figheight = 2.2
palette = sns.color_palette("pastel")
hatches = ["", "//", "xx", "\\\\", ".."]

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

def calculate_categories(raw_data):
    """Calculate values for each category"""
    wallet_data = raw_data.get('Wallet', {})
    
    categories = {
        'VM': {
            'QEMU': raw_data['VM']['QEMU'],
            'OVMF': raw_data['VM']['OVMF'],
            'Guest-OS': raw_data['VM']['Linux'],
            'Runtime': raw_data['VM']['Runtime']
        },
        'CVM': {
            'QEMU': raw_data['CVM']['QEMU'],
            'OVMF': raw_data['CVM']['OVMF'],
            'Guest-OS': raw_data['CVM']['Linux'],
            'Runtime': raw_data['CVM']['Runtime']
        },
        'Wallet': {
            'QEMU': wallet_data['QEMU'],
            'Monitor': wallet_data['Monitor'],
            'Guest-OS': wallet_data['Linux/OVMF'],
            'Runtime': wallet_data['Runtime'],
            'Zygote': wallet_data['Zygote'],
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke']
        },
        # Wallet empty
        'W-em': {
            'QEMU': 0,
            'Monitor': 0,
            'Guest-OS': 0,
            'Runtime': 0,
            'Zygote': wallet_data['Zygote'],
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke']
        },
        # Wallet semi-hot
        'W-wa': {
            'QEMU': 0,
            'Monitor': 0,
            'Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke']
        },
        # Wallet hot
        'W-hot': {
            'QEMU': 0,
            'Monitor': 0,
            'Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': wallet_data['Invoke']
        }
    }
    
    return categories

def create_plot(categories, output_dir):
    """Create stacked bar chart"""
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
    df.plot(kind='bar', stacked=True, ax=ax, color=palette, edgecolor='black', width=0.8)
    
    # Add hatches for better distinction
    bars = ax.patches
    n_bars = len(df)
    n_categories = len(df.columns)
    patterns = [h for h in hatches for _ in range(n_bars)]
    for bar, pattern in zip(bars, patterns):
        bar.set_hatch(pattern)
    
    # Add value labels on the bars
    for i, category in enumerate(df.index):
        total = 0
        for j, value in enumerate(df.loc[category]):
            if value > 0:  # Only show non-zero values
                total += value
        # Add total on top
        ax.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE)
    
    # Customize the plot
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    ax.set_xlabel('Variant', fontsize=TICKS_FONTSIZE)
    plt.xticks(fontsize=TICKS_FONTSIZE, rotation=0)
    ax.set_title('Boot Time', pad=5, fontsize=TITLE_FONTSIZE)
    
    # Enhance legend
    legend = plt.legend(bbox_to_anchor=(0.7, 0.98), loc='upper left', 
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines for better readability
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'boot_time.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'boot_time.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate stacked bar charts from boot time data')
    parser.add_argument('input_file', type=str, help='Path to the input file')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    raw_data = load_data(args.input_file)
    categories = calculate_categories(raw_data)
    
    # Create plots
    create_plot(categories, args.output_dir)
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()