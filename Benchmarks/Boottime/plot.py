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
ANNOTATION_SIZE = 4
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
            'Monitor/OVMF': raw_data['VM']['OVMF'],
            'Guest-OS': raw_data['VM']['Linux'],
            'Fn Invocation': raw_data['VM']['Runtime']
        },
        'CVM': {
            'QEMU': raw_data['CVM']['QEMU'],
            'Monitor/OVMF': raw_data['CVM']['OVMF'],
            'Guest-OS': raw_data['CVM']['Linux'],
            'Fn Invocation': raw_data['CVM']['Runtime']
        },
        'Wallet\n(cold)': {
            'QEMU': wallet_data['QEMU'],
            'Monitor/OVMF': wallet_data['Monitor'],
            'Guest-OS': wallet_data['Linux/OVMF'],
            # 'Runtime': wallet_data['Runtime'],
            # 'Zygote': wallet_data['Zygote'],
            # 'Trustlet': wallet_data['Trustlet'],
            # 'Invoke': wallet_data['Invoke']
            'Fn Invocation': wallet_data['Runtime'] + wallet_data['Zygote'] + wallet_data['Trustlet'] + wallet_data['Invoke']
        },
        # Wallet empty
        # 'W-em': {
        #     'QEMU': 0,
        #     'Monitor': 0,
        #     'Guest-OS': 0,
        #     'Runtime': 0,
        #     'Zygote': wallet_data['Zygote'],
        #     'Trustlet': wallet_data['Trustlet'],
        #     'Invoke': wallet_data['Invoke']
        #     'Fn Invocation': wallet_data['Zygote'] + wallet_data['Trustlet'] + wallet_data['Invoke']
        # },
        # Wallet semi-hot
        'Wallet\n(warm)': {
            'QEMU': 0,
            'Monitor/OVMF': 0,
            'Guest-OS': 0,
            # 'Runtime': 0,
            # 'Zygote': 0,
            # 'Trustlet': wallet_data['Trustlet'],
            # 'Invoke': wallet_data['Invoke']
            'Fn Invocation': wallet_data['Trustlet'] + wallet_data['Invoke']
        },
        # Wallet hot
        'Wallet\n(hot)': {
            'QEMU': 0,
            'Monitor/OVMF': 0,
            'Guest-OS': 0,
            # 'Runtime': 0,
            # 'Zygote': 0,
            # 'Trustlet': 0,
            'Fn Invocation': wallet_data['Invoke']
        },
        'Kata': {
            'Fn Invocation': raw_data['Kata Containers']['Total']
        },
        '\nGramine': {
            'Fn Invocation': raw_data['Gramine']['Total']
        },
        'Native': {
            'Fn Invocation': raw_data['Native']['Total']
        }
    }
    
    return categories

def create_plot(categories, output_dir, y_scale='linear', motivation=False):
    """Create stacked bar chart"""

    if motivation:
        motivation_categories = ['VM', 'CVM']
        categories = {k: categories[k] for k in motivation_categories if k in categories}
        figwidth = 2.2  # 3.3 inch for single column, 7 inch for double column
        figheight = 1.5
    else:
        figwidth = 3.3  # 3.3 inch for single column, 7 inch for double column
        figheight = 2.2

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
    ax.set_xlabel('Variant', fontsize=TICKS_FONTSIZE)
    plt.xticks(fontsize=TICKS_FONTSIZE, rotation=0)
    # ax.set_title('Boot Time', pad=5, fontsize=TITLE_FONTSIZE)
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Enhance legend
    if not motivation:
      legend = plt.legend(bbox_to_anchor=(0.63, 0.98), loc='upper left', 
                        borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
      legend.get_frame().set_edgecolor('black')

    # Increase the border a bit to fit the annotations
    if (y_scale == "linear"):
      ax.set_ylim(top=y_max + 0.1*y_max)
    else:
      ax.set_ylim(top=2*y_max)
    
    # Add gridlines for better readability
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)

    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plot_type = 'motivation_' if motivation else ''
    plt.savefig(output_dir / f'{plot_type}boot_time_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'{plot_type}boot_time_{y_scale}.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate stacked bar charts from boot time data')
    parser.add_argument('input_file', type=str, help='Path to the input file')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    raw_data = load_data(args.input_file)
    categories = calculate_categories(raw_data)
    
    # Create plots for all categories
    create_plot(categories, args.output_dir)
    create_plot(categories, args.output_dir, 'log')
    # Create plots for VM and CVM only for motivation
    create_plot(categories, args.output_dir, motivation=True)
    create_plot(categories, args.output_dir, 'log', motivation=True)
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()
