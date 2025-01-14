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
figwidth = 3.3 # 3.3 inch for single column, 7 inch for double column
figheight = 2.2
palette = sns.color_palette("pastel")
hatches = ["", "//", "xx", "\\\\", ".."]

def load_data(csv_path):
    """Load and parse CSV data"""
    df = pd.read_csv(csv_path)
    # Convert string values to numeric, replacing '-' with NaN
    df['Size (bytes)'] = pd.to_numeric(df['Size (bytes)'].replace('-', np.nan))
    return df

def calculate_categories(df):
    """Calculate values for each category"""
    monitor_cold = df[df['Measurement'] == 'measure_monitor_cold']['Average (ns)'].values[0]
    monitor_hot = df[df['Measurement'] == 'measure_monitor_hot']['Average (ns)'].values[0]
    zygote_cold = df[df['Measurement'] == 'measure_zygote_cold']['Average (ns)'].values[0]
    zygote_hot = df[df['Measurement'] == 'measure_zygote_hot']['Average (ns)'].values[0]
    trustlet_cold = df[df['Measurement'] == 'measure_trustlet_cold']['Average (ns)'].values[0]
    trustlet_hot = df[df['Measurement'] == 'measure_trustlet_hot']['Average (ns)'].values[0]
    function = df[df['Measurement'] == 'measure_function']['Average (ns)'].values[0]
    
    categories = {
        # CVM
        'CVM': {
            'CVM TCB': monitor_cold,
            'Monitor': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Function': 0
        },
        # CVM full
        'CVM-fu': {
            'CVM TCB': 3 * monitor_cold + zygote_cold + trustlet_cold + function,
            'Monitor': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Function': 0
        },
        # CVM short
        'CVM-sh': {
            'CVM TCB': monitor_cold + zygote_cold + trustlet_cold + function,
            'Monitor': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Function': 0
        },
        # Wallet cold
        'W-co': {
            'CVM TCB': 0,
            'Monitor': monitor_cold,
            'Zygote': zygote_cold,
            'Trustlet': trustlet_cold,
            'Function': function
        },
        # Wallet warm (semi-hot)
        'W-wa': {
            'CVM TCB': 0,
            'Monitor': monitor_hot,
            'Zygote': zygote_hot,
            'Trustlet': trustlet_cold,
            'Function': function
        },
        # Wallet hot
        'W-ho': {
            'CVM TCB': 0,
            'Monitor': monitor_hot,
            'Zygote': zygote_hot,
            'Trustlet': trustlet_hot,
            'Function': function
        }
    }
    
    return categories

def create_plot(categories, output_dir, y_scale='linear'):
    """Create stacked bar chart"""
    # Convert to DataFrame
    data = []
    for category, components in categories.items():
        row = {'Category': category}
        row.update(components)
        data.append(row)
    
    df = pd.DataFrame(data)
    df.set_index('Category', inplace=True)
    
    # Convert nanoseconds to milliseconds
    df = df / 1_000_000
    
    # Create the plot with increased size
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
    
    # Add value labels on the top bars
    for i, category in enumerate(df.index):
        total = 0
        for j, value in enumerate(df.loc[category]):
            if value > 0:  # Only show non-zero values
                x = i
                y = total + (value / 2)
                total += value
                # if value > df.values.max() * 0.05:  # Only show labels for visible segments
                    # ax.text(x, y, f'{value:.1f}', ha='center', va='center', fontsize=7)
        # Add total on top of each bar - choose the axis depending where the total is
        ax.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE)
    
    # Customize the plot
    ax.set_yscale(y_scale)
    # Tick size
    ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    # Fix xticks rotation
    plt.xticks(rotation=0)
    # y-axis label set in the middle of the plt
    ax.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
  
    # x-axis label
    ax.set_xlabel('Variant', fontsize=TICKS_FONTSIZE)
    # Title in the upper plot
    ax.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")

    # Insert legend in the top right position
    legend = ax.legend(bbox_to_anchor=(0.73, 0.97), loc='upper left', 
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines for better readability
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
       
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    plt.subplots_adjust(wspace=0, hspace=0.05)

    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'attestation_report_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / f'attestation_report_{y_scale}.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def create_cutoff_plot(categories, output_dir):
    """Create stacked bar chart"""
    # Convert to DataFrame
    data = []
    for category, components in categories.items():
        row = {'Category': category}
        row.update(components)
        data.append(row)
    
    df = pd.DataFrame(data)
    df.set_index('Category', inplace=True)
    
    # Convert nanoseconds to milliseconds
    df = df / 1_000_000
    
    # Create the plot with increased size
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(figwidth, figheight))

    ax1.set_ylim(2450, 2850)  # outliers only
    ax2.set_ylim(0, 7)  # most of the data
    
    # hide the spines between ax and ax2
    ax1.spines.bottom.set_visible(False)
    ax2.spines.top.set_visible(False)

    # hide the xaxis from the upper plot
    ax1.get_xaxis().set_visible(False)

    d = .5  # proportion of vertical to horizontal extent of the slanted line
    kwargs = dict(marker=[(-1, -d), (1, d)], markersize=TICKS_FONTSIZE,
                  linestyle="none", color='k', mec='k', mew=1, clip_on=False)
    ax1.plot([0, 1], [0, 0], transform=ax1.transAxes, **kwargs)
    ax2.plot([0, 1], [1, 1], transform=ax2.transAxes, **kwargs)

    # Plot stacked bars with wider bars
    df.plot(kind='bar', stacked=True, ax=ax1, color=palette, edgecolor='black', width=0.8)
    df.plot(kind='bar', stacked=True, ax=ax2, color=palette, edgecolor='black', width=0.8, legend=False)
    
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
                x = i
                y = total + (value / 2)
                total += value
                # if value > df.values.max() * 0.05:  # Only show labels for visible segments
                    # ax.text(x, y, f'{value:.1f}', ha='center', va='center', fontsize=7)
        # Add total on top of each bar - choose the axis depending where the total is
        if total > 2450:
            ax1.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE)
        else:
            ax2.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE)
    
    # Customize the plot
    # Tick size
    ax1.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax1.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    ax2.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax2.tick_params(axis='both', which='minor', labelsize=TICKS_FONTSIZE)
    # Fix xticks rotation
    plt.xticks(rotation=0)
    # y-axis label set in the middle of the plt
    # ax2.set_ylabel('Time (ms)', fontsize=TICKS_FONTSIZE)
    ax2.annotate(
        'Time (ms)',  # Text to annotate
        xy=(-0.12, 5),  # The point to annotate (data coordinates)
        xytext=(-50, 15),  # Text location (offset coordinates)
        textcoords='offset points',  # Interpret xytext as an offset from xy
        rotation=90,  # Rotate the label vertically
        va='center',  # Align text vertically to the center
        fontsize=TICKS_FONTSIZE,  # Font size
    )
  
    # x-axis label
    ax2.set_xlabel('Variant', fontsize=TICKS_FONTSIZE)
    # Title in the upper plot
    ax1.set_title('Lower is better ↓', pad=5, fontsize=TITLE_FONTSIZE, color="navy")
    
    # Insert legend in the top right position
    legend = ax1.legend(bbox_to_anchor=(0.73, 0.97), loc='upper left', 
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    legend.get_frame().set_edgecolor('black')
    
    # Add gridlines for better readability
    ax1.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax2.yaxis.grid(True, linestyle='--', alpha=0.7)
       
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    plt.subplots_adjust(wspace=0, hspace=0.05)

    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'attestation_report_cutoff.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(output_dir / 'attestation_report_cutoff.png', format='png', dpi=300, bbox_inches='tight')
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate stacked bar charts from CSV data')
    parser.add_argument('csv_file', type=str, help='Path to the CSV file')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    df = load_data(args.csv_file)
    categories = calculate_categories(df)
    
    # Create plots
    create_plot(categories, args.output_dir)
    create_plot(categories, args.output_dir, 'log')
    create_cutoff_plot(categories, args.output_dir)
    print(f"Plots saved in {args.output_dir}")

if __name__ == "__main__":
    main()