#!/usr/bin/env python3

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import re
import subprocess

# Import centralized plotting configuration
import sys
sys.path.append('..')
from motivation_plotting_config import *

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
        # 'LibOS\n(Gramine)': {
        'LibOS': { 
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': raw_data['Gramine']['Runtime'],
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['Gramine']['Invoke'],
        },
        # 'Containers\n(Kata)': {
        'Container': {
            'VMM (QEMU)': raw_data['Kata Containers']['QEMU'],
            'Monitor': 0,
            'Firmware (OVMF)': raw_data['Kata Containers']['OVMF'],
            'OS/Guest-OS': raw_data['Kata Containers']['Linux'],
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['Kata Containers']['Runtime'],
        },
        # 'VM\n(KVM-Linux)': {
        'Linux VM': { 
            'VMM (QEMU)': raw_data['VM']['QEMU'],
            'Monitor': 0,
            'Firmware (OVMF)': raw_data['VM']['OVMF'],
            'OS/Guest-OS': raw_data['VM']['Linux'],
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['VM']['Runtime'],
        },
        # 'CVM\n(SEV-SNP)': {
        'CVM': {  
            'VMM (QEMU)': raw_data['CVM']['QEMU'],
            'Monitor': 0,
            'Firmware (OVMF)': raw_data['CVM']['OVMF'],
            'OS/Guest-OS': raw_data['CVM']['Linux'],
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': raw_data['CVM']['Runtime'],
        },
        'Wallet\n(init)': {
            'VMM (QEMU)': wallet_data['QEMU'],
            'Monitor': wallet_data['Monitor'],
            'Firmware (OVMF)': wallet_data['OVMF'],
            'OS/Guest-OS': wallet_data['Linux'],
            'Runtime': 0,
            'Zygote': 0,
            'Trustlet': 0,
            'Invoke': 0,
        },
        'Wallet\n(cold)': {
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': wallet_data['Runtime'],
            'Zygote': wallet_data['Zygote'],
            'Trustlet': wallet_data['Trustlet'],
            'Invoke': wallet_data['Invoke'],
        },
        # Wallet lukewarm
        'Wallet\n(lukewarm)': {
            'VMM (QEMU)': 0,
            'Monitor': 0,
            'Firmware (OVMF)': 0,
            'OS/Guest-OS': 0,
            'Runtime': 0,
            'Zygote': 0,
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
    
    # Create standardized cutoff plot
    fig, (ax1, ax2) = create_standardized_cutoff_plot(ax_height = 0.7, bottom_margin= 0.45, top_margin=0.65)

    # Set y-axis limits with a break
    ax1.set_ylim(400, 14200)  # upper section for high values
    ax2.set_ylim(0, 240)      # lower section for most data
    
    # Add break marks
    apply_broken_axis_style(ax1, ax2)

    # Plot stacked bars with wider bars
    df.plot(kind='bar', stacked=True, ax=ax1, color=PALETTE_PASTEL, linewidth=0, edgecolor='black', width=0.8, legend=False)
    df.plot(kind='bar', stacked=True, ax=ax2, color=PALETTE_PASTEL, linewidth=0, edgecolor='black', width=0.8, legend=False)
    
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
        if total > 50:
            ax1.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
        else:
            ax2.text(i, total, f'{total:.1f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
    
    # Apply consistent styling
    apply_consistent_style(ax1, title=LOWER_BETTER_TITLE)
    apply_consistent_style(ax2)
    
    # Fix xticks rotation
    plt.xticks(rotation=90)
    
    # Add y-axis label in the middle
    create_annotation_y_label(ax2, 'Time (ms)', position=(0.52, 220))
    
    # Add legend at the center top
    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, loc='center', bbox_to_anchor=(0.55, 0.85), 
               edgecolor='black', borderaxespad=0., fontsize=LEGEND_FONTSIZE, 
               frameon=True, ncols=2)
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'boot_time_cutoff.pdf', format='pdf', dpi=300, bbox_inches=None)
    plt.savefig(output_dir / 'boot_time_cutoff.png', format='png', dpi=300, bbox_inches=None)
    
    plt.close()

def create_plot(categories, output_dir, y_scale='linear'):
    """Create standard stacked bar chart"""
    # Convert to DataFrame
    data = []
    for category, components in categories.items():
        row = {'Category': category}
        row.update(components)
        data.append(row)

    df = pd.DataFrame(data)
    df.set_index('Category', inplace=True)
    
    # Create standardized plot
    fig, ax = create_standardized_plot()
    
    # Plot stacked bars with wider bars
    df.plot(kind='bar', stacked=True, ax=ax, color=PALETTE_PASTEL, linewidth=0, 
            edgecolor='black', width=0.6)
    
    # Add hatches for better distinction
    bars = ax.patches
    n_bars = len(df)
    n_categories = len(df.columns)
    patterns = [h for h in HATCHES for _ in range(n_bars)]
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
    
    # Apply consistent styling
    apply_consistent_style(ax, 
                         title=LOWER_BETTER_TITLE,
                         xlabel="",
                         ylabel="Time (ms)")
    
    # Customize the plot
    ax.set_yscale(y_scale)
    plt.xticks(fontsize=TICKS_FONTSIZE, rotation=25)
    
    # Increase the border a bit to fit the annotations
    if y_scale == "linear":
      ax.set_ylim(top=y_max + 0.1*y_max)
    else:
      ax.set_ylim(top=2*y_max)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / f'boot_time_{y_scale}.pdf', format='pdf', dpi=300, bbox_inches=None)
    plt.savefig(output_dir / f'boot_time_{y_scale}.png', format='png', dpi=300, bbox_inches=None)
    
    plt.close()

def print_summary(categories):
    """Print a summary of each bar's total time and breakdown"""
    print("\n==== Boot Time Summary ====")
    for category, components in categories.items():
        total = sum(components.values())
        print(f"\n{category}:")
        print(f"  Total: {total:.2f} ms")
        print("  Breakdown:")
        for component, value in components.items():
            if value > 0:
                percentage = (value / total) * 100
                print(f"    - {component}: {value:.2f} ms ({percentage:.1f}%)")

def main():
    parser = argparse.ArgumentParser(description='Generate stacked bar charts from boot time data')
    parser.add_argument('input_file', type=str, help='Path to the input file')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Load and process data
    raw_data = load_data(args.input_file)
    categories = calculate_categories(raw_data)

    # Create plots for all categories
    create_cutoff_plot(categories, args.output_dir)
    create_plot(categories, args.output_dir)
    create_plot(categories, args.output_dir, 'log')

    print(f"Plots saved in {args.output_dir}")
    
    # Print summary of each bar
    print_summary(categories)

if __name__ == "__main__":
    main()