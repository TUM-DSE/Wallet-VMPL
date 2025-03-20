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
TICKS_FONTSIZE = 6
LEGEND_FONTSIZE = 6
ANNOTATION_SIZE = 4
palette = sns.color_palette("pastel")
hatches = ["", "//", "xx", "\\\\", ".."]

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

def calculate_categories(raw_data):
    """Calculate values for each category"""
    wallet_data = raw_data.get('Wallet', {})
    
    categories = {
        'Native': {
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['Native']['Total'],
        },
        'LibOS\n(Gramine)': {
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['Gramine']['Total'],
        },
        'Containers\n(Kata)': {
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['Kata Containers']['Total'],
        },
        'VM\n(KVM-Linux)': {
            'VMM (QEMU)': raw_data['VM']['QEMU'],
            'Monitor': 0,
            'Firmware (OVMF)': raw_data['VM']['OVMF'],
            'OS/Guest-OS': raw_data['VM']['Linux'],
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['VM']['Runtime'],
        },
        'CVM\n(SEV-SNP)': {
            'VMM (QEMU)': raw_data['CVM']['QEMU'],
            'Monitor': 0,
            'Firmware (OVMF)': raw_data['CVM']['OVMF'],
            'OS/Guest-OS': raw_data['CVM']['Linux'],
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['CVM']['Runtime'],
        },
        'Wallet\n(cold)': {
            'VMM (QEMU)': wallet_data['QEMU'],
            'Monitor': wallet_data['Monitor'],
            'Firmware (OVMF)': wallet_data['OVMF'],
            'OS/Guest-OS': wallet_data['Linux'],
            'Runtime': wallet_data['Runtime'],
            'Zygote': wallet_data['Zygote'],
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke'],
        },
        # Wallet warm
        'Wallet\n(warm)': {
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke'],
        },
        # Wallet hot
        'Wallet\n(hot)': {
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': wallet_data['Invoke'],
        }        
    }
    
    return categories

def create_cutoff_plot(categories, output_dir, y_scale='linear'):
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
        if total > 50:
            ax1.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
        else:
            ax2.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
    
    # Customize the plot
    # Tick size
    ax1.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax1.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    ax2.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax2.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    
    # Fix xticks rotation
    plt.xticks(rotation=0)
    
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
    ax2.set_xlabel('Variant', fontsize=TICKS_FONTSIZE)
    
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

    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'boot_time_cutoff.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'boot_time_cutoff.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def create_plot(categories, output_dir, y_scale='linear', motivation=False):
    """Create stacked bar chart"""

    if motivation:
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
      legend = plt.legend(bbox_to_anchor=(0.01, 0.98), loc='upper left', 
                        borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, framealpha=0.5)
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
    
    print(categories)
    # Create plots for all categories
    create_cutoff_plot(categories, args.output_dir)
    create_plot(categories, args.output_dir)
    create_plot(categories, args.output_dir, 'log')
    # Create plots for VM and CVM only for motivation
    create_plot(categories, args.output_dir, motivation=True)
    create_plot(categories, args.output_dir, 'log', motivation=True)
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()
