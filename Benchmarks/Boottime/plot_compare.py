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
                # Convert milliseconds to seconds here
                measurements[component.strip()] = float(value_match.group(1)) / 1000.0
        
        data[section_name] = measurements
    
    return data

def calculate_categories(raw_data):
    """Calculate values for each category"""
    wallet_data = raw_data.get("Wallet", {})
    wallet_data_pre = raw_data.get("Wallet Preallocation", {})
    # name = 'Wallet w/o\npreallocation'
    wallet_data_name = 'w/o prealloc'
    categories = {
        wallet_data_name : {
           'VMM (QEMU)': wallet_data['QEMU'],
            'Monitor': wallet_data['Monitor'],
            'Firmware (OVMF)': wallet_data['OVMF'],
            'Guest-OS': wallet_data['Linux'],
            'Runtime': wallet_data['Runtime'],
            'Zygote': wallet_data['Zygote'],
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke'],
        },
        # Wallet warm
        # 'Wallet\n(warm)': {
        #     'VMM (QEMU)': 0,
        #     'Monitor': 0,
        #     'Firmware (OVMF)': 0,
        #     'Guest-OS': 0,
        #     'Runtime': 0,
        #     'Zygote': 0,
        #     'Trustlet': wallet_data['Trustlet'],
        #     'Invoke': wallet_data['Invoke'],
        # },
        # Wallet hot
        # 'Wallet\n(hot)': {
        #     'VMM (QEMU)': 0,
        #     'Monitor': 0,
        #     'Firmware (OVMF)': 0,
        #     'Guest-OS': 0,
        #     'Runtime': 0,
        #     'Zygote': 0,
        #     'Trustlet': 0,
        #     'Invoke': wallet_data['Invoke'],
        # }
    }
    wallet_data = wallet_data_pre
    # wallet_data_pre_name = 'Wallet w/\npreallocation'
    wallet_data_pre_name = 'w/ prealloc'
    categories2 = {
        wallet_data_pre_name: {
           'VMM (QEMU)': wallet_data['QEMU'],
            'Monitor': wallet_data['Monitor'],
            'Firmware (OVMF)': wallet_data['OVMF'],
            'Guest-OS': wallet_data['Linux'],
            'Runtime': wallet_data['Runtime'],
            'Zygote': wallet_data['Zygote'],
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke'],
        },
        # Wallet warm
        # 'Wallet*\n(warm)': {
        #     'VMM (QEMU)': 0,
        #     'Monitor': 0,
        #     'Firmware (OVMF)': 0,
        #     'Guest-OS': 0,
        #     'Runtime': 0,
        #     'Zygote': 0,
        #     'Trustlet': wallet_data['Trustlet'],
        #     'Invoke': wallet_data['Invoke'],
        # },
        # # Wallet hot
        # 'Wallet*\n(hot)': {
        #     'VMM (QEMU)': 0,
        #     'Monitor': 0,
        #     'Firmware (OVMF)': 0,
        #     'Guest-OS': 0,
        #     'Runtime': 0,
        #     'Zygote': 0,
        #     'Trustlet': 0,
        #     'Invoke': wallet_data['Invoke'],
        # }
    }

    categories = categories | categories2

    return categories

def create_plot(categories, output_dir, y_scale='linear', motivation=False):
    """Create stacked bar chart"""
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
        df.plot(kind='bar', stacked=True, ax=ax, color=palette, linewidth = 0, edgecolor='black', width=0.8)
    
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
    ax.set_ylabel('Time (s)', fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    ax.yaxis.offsetText.set_fontsize(TICKS_FONTSIZE)
    # ax.set_xlabel('Variant', fontsize=TICKS_FONTSIZE)
    ax.set_xlabel('', fontsize=TICKS_FONTSIZE)
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
    
    plt.savefig(output_dir / f'boot_time_opt_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'boot_time_opt_{y_scale}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'boot_time_opt_{y_scale}.pdf')
    
    plt.close()

def create_configurable_triple_cutoff_plot(categories, output_dir, upper_range=(248, 258), 
                                        middle_range=(232, 247), lower_range=(0, 16), 
                                        filename_prefix='boot_time_opt_triple_cutoff', figsize=(1.5, 1.8)):
    """Create stacked bar chart with two broken y-axes for boot time data with configurable ranges"""
    # Convert to DataFrame
    data = []
    for category, components in categories.items():
        row = {'Category': category}
        row.update(components)
        data.append(row)
    
    df = pd.DataFrame(data)
    df.set_index('Category', inplace=True)
    
    figwidth, figheight = figsize
    # Create the plot with specified size - now with three subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True, figsize=(figwidth, figheight))

    # Set y-axis limits with two breaks - configurable ranges
    ax1.set_ylim(upper_range)     # upper section for highest values
    ax2.set_ylim(middle_range)    # middle section for medium values
    ax3.set_ylim(lower_range)     # lower section for lowest values
    
    # Hide the spines between axes
    ax1.spines.bottom.set_visible(False)
    ax2.spines.top.set_visible(False)
    ax2.spines.bottom.set_visible(False)
    ax3.spines.top.set_visible(False)

    # Hide the xaxis from the upper and middle plots
    ax1.get_xaxis().set_visible(False)
    ax2.get_xaxis().set_visible(False)

    # Add break marks between the plots
    d = .5  # proportion of vertical to horizontal extent of the slanted line
    kwargs = dict(marker=[(-1, -d), (1, d)], markersize=TICKS_FONTSIZE,
                  linestyle="none", color='k', mec='k', mew=1, clip_on=False)
    ax1.plot([0, 1], [0, 0], transform=ax1.transAxes, **kwargs)
    ax2.plot([0, 1], [1, 1], transform=ax2.transAxes, **kwargs)
    ax2.plot([0, 1], [0, 0], transform=ax2.transAxes, **kwargs)
    ax3.plot([0, 1], [1, 1], transform=ax3.transAxes, **kwargs)

    # Plot stacked bars with wider bars
    df.plot(kind='bar', stacked=True, ax=ax1, color=palette, linewidth=0, edgecolor='black', width=0.3, legend=False)
    df.plot(kind='bar', stacked=True, ax=ax2, color=palette, linewidth=0, edgecolor='black', width=0.3, legend=False)
    df.plot(kind='bar', stacked=True, ax=ax3, color=palette, linewidth=0, edgecolor='black', width=0.3, legend=False)
    
    # Add hatches for better distinction
    bars1 = ax1.patches
    bars2 = ax2.patches
    bars3 = ax3.patches
    n_bars = len(df)
    n_categories = len(df.columns)
    patterns = [h for h in hatches for _ in range(n_bars)]
    for bar, pattern in zip(bars1, patterns):
        bar.set_hatch(pattern)
    for bar, pattern in zip(bars2, patterns):
        bar.set_hatch(pattern)
    for bar, pattern in zip(bars3, patterns):
        bar.set_hatch(pattern)
    
    # Add value labels on the top bars
    for i, category in enumerate(df.index):
        total = 0
        for j, value in enumerate(df.loc[category]):
            if value > 0:  # Only show non-zero values
                total += value
        
        # Add total on top of each bar - choose the axis depending where the total is
        if total > middle_range[1]:  # If total is in the upper range
            ax1.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
        elif total > lower_range[1]:  # If total is in the middle range
            ax2.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
        else:  # If total is in the lower range
            ax3.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
    
    # Customize the plot
    # Tick size for all axes
    for ax in [ax1, ax2, ax3]:
        ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
        ax.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    
    # Fix xticks rotation
    plt.xticks(rotation=0)  # Changed to 0 rotation since we have only two categories
    
    # Add y-axis label in the middle of the middle plot
    fig.text(-0.03, 0.5, 'Time (s)', va='center', rotation='vertical', fontsize=TICKS_FONTSIZE)
    
    # x-axis label
    ax3.set_xlabel('', fontsize=TICKS_FONTSIZE)
    
    # Title in the upper plot
    ax1.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # legend = ax1.legend(bbox_to_anchor=(0.03, 0.96), loc='upper left',
                      #  borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE-1, ncol=1)
    # legend.get_frame().set_edgecolor('black')

    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(0.22, 0.88), fontsize=LEGEND_FONTSIZE-1, frameon=True, edgecolor='black')

    # Add gridlines for better readability
    ax1.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax2.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax3.yaxis.grid(True, linestyle='--', alpha=0.7)
       
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    # Adjust subplot spacing - make it tighter for broken axis look
    plt.subplots_adjust(wspace=0, hspace=0.05)

    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'{filename_prefix}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'{filename_prefix}.png', format='png', dpi=300, bbox_inches='tight')
    crop_pdf(output_dir / f'{filename_prefix}.pdf')
    
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

    figsize = (3.3/2, 2.0)
    create_configurable_triple_cutoff_plot(categories, args.output_dir, figsize=figsize)
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()
