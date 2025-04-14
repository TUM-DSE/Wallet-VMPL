#!/usr/bin/env python3

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import csv

# Import centralized plotting configuration
import sys
sys.path.append('..')
from motivation_plotting_config import *

def get_monitor_measurement_time(csv_path):
    with open(csv_path, 'r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        
        for row in csv_reader:
            if row['Measurement'] == 'measure_monitor_cold':
                return float(row['Average (ns)'])

    raise ValueError(f"measure_monitor_cold not found in {csv_path}")


def read_breakdown_csv(csv_path):
    """
    Read the breakdown CSV file and calculate averages for each measurement.
    
    Returns:
        dict: Dictionary with average times for each measurement
    """
    df = pd.read_csv(csv_path)
    
    # Calculate averages for the required columns
    averages = {
        'Zygote': df['zygote_measure'].mean(),
        'Input': df['input_measure'].mean(),
        'Trustlet': df['trustlet_measure'].mean(),
        'Output': df['output_measure'].mean()
    }
    
    return averages


def create_breakdown_plot(averages, monitor_measure_time, output_path_base):
    """
    Create a bar plot showing the breakdown of measurements.
    
    Args:
        averages (dict): Dictionary with average times for each measurement
        monitor_measure_time (float): Monitor measurement time
        output_path_base (str or Path): Base path to save the output plots (without extension)
    """
    # Complete data with monitor measurement
    data = {
        'Monitor': monitor_measure_time,
        'Zygote': averages['Zygote'],
        'Trustlet': averages['Trustlet'],
        'Input': averages['Input'],
        'Output': averages['Output']
    }
    
    # Create the plot with the specified order
    order = ['Monitor', 'Zygote', 'Trustlet', 'Input', 'Output']
    
    # Create standardized plot using utility functions
    fig, ax = create_standardized_plot(
        ax_width=AX_WIDTH, 
        ax_height=AX_HEIGHT*1.1
    )
    
    # Convert nanoseconds to milliseconds
    values = [data[key]/1_000_000 for key in order]
    
    # Create the bar plot with colors from config
    bars = ax.bar(order, values, color=PALETTE_PASTEL, width=0.6)
    
    # Apply consistent styling from config
    apply_consistent_style(
        ax,
        title='Attestation Component Breakdown',
        ylabel='Time (ms)',
        grid=False,
    )
    
    # Add values on top of each bar
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}',
                ha='center', va='bottom', fontsize=ANNOTATION_SIZE)
    
    # Format x-axis labels
    ax.set_xticklabels(order, fontsize=TICKS_FONTSIZE)
    
    # Save as PNG
    png_path = f"{output_path_base}.png"
    plt.savefig(png_path, dpi=300, bbox_inches='tight')
    print(f"Saved PNG to {png_path}")
    
    # Save as PDF and crop
    pdf_path = f"{output_path_base}.pdf"
    plt.savefig(pdf_path, format='pdf', bbox_inches='tight')
    crop_pdf(pdf_path)
    print(f"Saved and cropped PDF to {pdf_path}")
    
    plt.close()
    
    return fig

def create_cutoff_plot(averages, output_dir):
    """Create bar chart with broken y-axis showing individual measurement components"""

    # Convert dictionary to DataFrame format with the right structure
    categories = ['Monitor', 'Zygote', 'Trustlet', 'Input', 'Output']
    df = pd.DataFrame({'Value': [averages[cat] for cat in categories]}, index=categories)
    
    # Convert nanoseconds to milliseconds
    df = df / 1_000_000
    
    # Create standardized cutoff plot
    fig, (ax1, ax2) = create_standardized_cutoff_plot(ax_height=0.95, top_margin=0.2, bottom_margin=0.3)

    # Set y-axis limits
    ax1.set_ylim(800, 1200)  # Zygote
    ax2.set_ylim(0, 7)       # most of the data
    
    # Add break marks
    apply_broken_axis_style(ax1, ax2)

    # Plot individual bars
    bars1 = ax1.bar(df.index, df['Value'], color=PALETTE_PASTEL, 
                   linewidth=0, edgecolor='black', width=0.6)
    bars2 = ax2.bar(df.index, df['Value'], color=PALETTE_PASTEL,
                   linewidth=0, edgecolor='black', width=0.6)
    
    # Add hatches for better distinction
    patterns = HATCHES[:len(df)]
    for i, bar in enumerate(bars1):
        bar.set_hatch(patterns[i])
    for i, bar in enumerate(bars2):
        bar.set_hatch(patterns[i])
    
    # Add value labels on the bars
    for i, value in enumerate(df['Value']):
        # Decide which axis to add label based on value height
        if value > 800:  # Values that would appear in top axis
            ax1.text(i, value, f'{value:.2f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
        else:  # Values that would appear in bottom axis (skip very small values)
            ax2.text(i, value, f'{value:.2f}', ha='center', va='bottom', fontsize=LEGEND_FONTSIZE-2)
    
    # Apply consistent styling
    apply_consistent_style(ax1, title=LOWER_BETTER_TITLE)
    apply_consistent_style(ax2)
    
    # Fix xticks rotation and add size annotations
    plt.xticks(rotation=0)
    
    # Add size annotations below labels
    size_annotations = ['', '(60MB)', '(4KB)', '(4KB)', '(4KB)']
    for i, category in enumerate(categories):
        # Add the size annotation below each category label
        if i > 0:  # Skip Monitor (no size annotation needed)
            ax2.text(i, -2.0, size_annotations[i], ha='center', va='top', fontsize=LEGEND_FONTSIZE-2)
    
    # Add y-axis label in the middle
    create_annotation_y_label(ax2, 'Time (ms)', position=(0.2, 6.5))
    
    # Save plots
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_dir / 'attestation_breakdown_cutoff.pdf', format='pdf', dpi=300, bbox_inches=None)
    plt.savefig(output_dir / 'attestation_breakdown_cutoff.png', format='png', dpi=300, bbox_inches=None)
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate breakdown bar charts from CSV data')
    parser.add_argument('--csv_file', type=str, help='Path to the CSV file of the attestation microbenchmark', default="./results.csv")
    parser.add_argument('--breakdown_csv_file', type=str, help='Path to the CSV file of the breakdown attestation microbenchmark', default="./breakdown/result.csv")
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Get the monitor measurement time
    monitor_measure_time = get_monitor_measurement_time(args.csv_file)
    print(f"Monitor measurement time: {monitor_measure_time} ns ({monitor_measure_time/1_000_000:.2f} ms)")
    
    # Read breakdown data
    averages = read_breakdown_csv(args.breakdown_csv_file)
    averages["Monitor"] = monitor_measure_time
    print("Average measurements:")
    for name, value in averages.items():
        print(f"  {name}: {value} ns ({value/1_000_000:.2f} ms)")
    
    # Create and save the regular plot (both PNG and PDF)
    regular_output_path_base = output_dir / "attestation_breakdown"
    create_breakdown_plot(averages, monitor_measure_time, regular_output_path_base)
    
    # Create and save the cut-off plot (both PNG and PDF)
    create_cutoff_plot(averages, output_dir)

if __name__ == "__main__":
    main()