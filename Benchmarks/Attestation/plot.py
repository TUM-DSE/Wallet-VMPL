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
        'CVM\n(SEV-SNP)': {
            'CVM TCB': monitor_cold + zygote_cold + trustlet_cold + function,
            'Monitor': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Function': 0
        },
        # Wallet cold
        'Wallet\n(cold)': {
            'CVM TCB': 0,
            'Monitor': monitor_cold,
            'Zygote': zygote_cold,
            'Trustlet': trustlet_cold,
            'Function': function
        },
        # Wallet lukewarm
        'Wallet\n(lukewarm)': {
            'CVM TCB': 0,
            'Monitor': monitor_hot,
            'Zygote': zygote_hot,
            'Trustlet': trustlet_cold,
            'Function': function
        },
        # Wallet warm
        'Wallet\n(warm)': {
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
    
    # Create standardized plot
    fig, ax = create_standardized_plot()
    
    # Plot stacked bars with wider bars
    df.plot(kind='bar', stacked=True, ax=ax, color=PALETTE_PASTEL, linewidth=0, edgecolor='black', width=0.6)
    
    # Add hatches for better distinction
    bars = ax.patches
    n_bars = len(df)
    n_categories = len(df.columns)
    patterns = [h for h in HATCHES for _ in range(n_bars)]
    for bar, pattern in zip(bars, patterns):
        bar.set_hatch(pattern)
    
    # Add value labels on the top bars
    for i, category in enumerate(df.index):
        total = 0
        for j, value in enumerate(df.loc[category]):
            if value > 0:  # Only show non-zero values
                total += value
        # Add total on top of each bar
        ax.text(i, total, f'{total:.3f}', ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
    
    # Apply consistent styling
    apply_consistent_style(ax, 
                         title=LOWER_BETTER_TITLE,
                         xlabel="",
                         ylabel="Time (ms)")
    
    # Customize the plot
    ax.set_yscale(y_scale)
    plt.xticks(rotation=0)
    
    # Insert legend in the top right position
    legend = ax.legend(bbox_to_anchor=(0.73, 0.97), loc='upper left', 
                     borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE)
    legend.get_frame().set_edgecolor('black')
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'attestation_report_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches=None)
    plt.savefig(output_dir / f'attestation_report_{y_scale}.png', format='png', dpi=300, bbox_inches=None)
    
    plt.close()

def create_cutoff_plot(categories, output_dir):
    """Create stacked bar chart with broken y-axis"""
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
    
    # Create standardized cutoff plot
    fig, (ax1, ax2) = create_standardized_cutoff_plot(ax_height = 0.95, top_margin = 0.2, bottom_margin = 0.3)

    # Set y-axis limits
    ax1.set_ylim(2745, 2749.5)  # outliers only
    ax2.set_ylim(0, 7)        # most of the data
    
    # Add break marks
    apply_broken_axis_style(ax1, ax2)

    # Plot stacked bars with wider bars
    df.plot(kind='bar', stacked=True, ax=ax1, color=PALETTE_PASTEL, linewidth=0, edgecolor='black', width=0.8, legend=False)
    df.plot(kind='bar', stacked=True, ax=ax2, color=PALETTE_PASTEL, linewidth=0, edgecolor='black', width=0.8)
    
    # Add hatches for better distinction
    bars1 = ax1.patches
    bars2 = ax2.patches
    n_bars = len(df)
    n_categories = len(df.columns)
    patterns = [h for h in HATCHES for _ in range(n_bars)]
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
        if total > 2450:
            ax1.text(i, total, f'{total:.3f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
        else:
            ax2.text(i, total, f'{total:.3f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
    
    # Apply consistent styling
    apply_consistent_style(ax1, title=LOWER_BETTER_TITLE)
    apply_consistent_style(ax2)
    
    # Fix xticks rotation
    plt.xticks(rotation=0)
    
    # Add y-axis label in the middle
    create_annotation_y_label(ax2, 'Time (ms)', position=(0, 6.5))
    
    # Position legend at the center top
    legend = ax2.legend(loc='center', bbox_to_anchor=(0.73, 1.3), 
                       borderaxespad=0., frameon=True, fontsize=LEGEND_FONTSIZE, ncols=1)
    legend.get_frame().set_edgecolor('black')
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'attestation_report_cutoff.pdf', format='pdf', dpi=300, bbox_inches=None)
    plt.savefig(output_dir / 'attestation_report_cutoff.png', format='png', dpi=300, bbox_inches=None)
    
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