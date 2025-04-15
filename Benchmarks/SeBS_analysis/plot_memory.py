#!/usr/bin/env python3

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import pprint as pprint
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
figwidth = 3.3  # 3.3 inch for single column, 7 inch for double column
figheight = 2.0
figheight2 = 1.8

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer',
    '311.compression',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    '504.dna-visualisation',
    #'411.image-recognition'
]

def crop_pdf(input_path):
    """Use pdfcrop to crop the PDF file."""
    try:
        subprocess.run(['pdfcrop', input_path, input_path], check=True)
        print(f"Successfully cropped {input_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error cropping PDF {input_path}: {e}")
    except FileNotFoundError:
        print("pdfcrop command not found. Please install texlive-extra-utils package.")

def plot_memory_usage(csv_path="memory.csv"):
    """Read memory usage data and plot cow vs no_cow comparison."""
    # Check if file exists
    if not Path(csv_path).exists():
        print(f"Error: {csv_path} does not exist.")
        return None
    
    # Read the CSV file
    df = pd.read_csv(csv_path)

    # keep rows with 'type' == 'wallet'
    df = df[df['type'] == 'wallet']
    # drop unnecessary columns: 'type', 'total'
    df = df.drop(columns=['type', 'total'])
    
    # Group by benchmark and calculate the average
    avg_memory = df.groupby('bench').mean().reset_index()

    # the csv contains number of 4K pages, convert to bytes
    avg_memory['cow'] = avg_memory['cow'] * 4096
    avg_memory['no_cow'] = avg_memory['no_cow'] * 4096
    
    # Convert to MB
    avg_memory['cow_mb'] = avg_memory['cow'] / 1024 / 1024
    avg_memory['no_cow_mb'] = avg_memory['no_cow'] / 1024 / 1024
    
    # Define custom order for benchmarks
    custom_order = {
        '210.thumbnailer': 0,
        '502.graph-mst': 1,
        '110.dynamic-html': 2,
        '501.graph-pagerank': 3,
        '504.dna-visualisation': 4,
        '503.graph-bfs': 5,
        '311.compression': 6,
        #'411.image-recognition': 7,
    }
    
    # Create an order column and sort by it
    avg_memory['order'] = avg_memory['bench'].map(custom_order)
    avg_memory = avg_memory.sort_values('order')
    
    # Set up the plot
    fig, ax = plt.subplots(figsize=(figwidth, figheight2))
    
    # Define positions for the bars
    benchmarks = avg_memory['bench']
    x = np.arange(len(benchmarks))
    width = 0.35
    
    # Define styling
    len2 = 2  # We have 2 categories (cow and no_cow)
    palette = sns.color_palette("pastel", n_colors=len2)
    hatches = ["", "//", "xx", "\\\\", ".."]
    linestyles = ["-", "--", "-.", ":", "-"]
    
    # Create the bars with the new styling (using MB values)
    cow_bars = ax.bar(x - width/2, avg_memory['cow_mb'], width, label='CoW shared', 
                      color=palette[0], hatch=hatches[0], 
                      edgecolor='black', linewidth=0.0)
    no_cow_bars = ax.bar(x + width/2, avg_memory['no_cow_mb'], width, label='Non-shared', 
                         color=palette[1], hatch=hatches[1], 
                         edgecolor='black', linewidth=0.0)
    
    # Add value annotations with MB formatting
    for bar in cow_bars:
        height = bar.get_height()
        ax.annotate(f'{height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 1),
                    textcoords="offset points",
                    ha='center', va='bottom',
                    fontsize=ANNOTATION_SIZE)
    
    for bar in no_cow_bars:
        height = bar.get_height()
        ax.annotate(f'{height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 1),
                    textcoords="offset points",
                    ha='center', va='bottom',
                    fontsize=ANNOTATION_SIZE)
    
    # Set labels and title with MB units
    ax.set_ylabel('Memory Usage (MB)', fontsize=TICKS_FONTSIZE)
    ax.set_ylim([0,1500])
    ax.set_title('Memory Usage', fontsize=TITLE_FONTSIZE)
    ax.tick_params(axis='both', which='major', labelsize=TICKS_FONTSIZE)
    ax.set_xticks(x)
    
    # Clean up benchmark names for display
    clean_benchmark_names = [b.split('.', 1)[1] for b in benchmarks]
    ax.set_xticklabels(clean_benchmark_names, fontsize=TICKS_FONTSIZE, rotation=15, ha='right')
    
    # Add grid with custom linestyle
    ax.grid(axis='y', linestyle=linestyles[0], alpha=0.7)
    
    # Legend
    ax.legend(fontsize=LEGEND_FONTSIZE)
    
    plt.tight_layout()
    plt.savefig('output/wallet_memory_usage_comparison.pdf', bbox_inches='tight')
    plt.savefig('output/wallet_memory_usage_comparison.png', dpi=300, bbox_inches='tight')
    crop_pdf('output/wallet_memory_usage_comparison.pdf')
    plt.close()
    
    return avg_memory

def main():
    # Plot memory usage and get the data
    avg_memory = plot_memory_usage()
    
    if avg_memory is not None:
        # Print detailed summary (converting to MB for output)
        print("\nMemory Usage Analysis:")
        
        total_cow = 0
        total_no_cow = 0
        
        for _, row in avg_memory.iterrows():
            bench = row['bench']
            cow_mem = row['cow'] / 1024 / 1024 # Convert to MB
            no_cow_mem = row['no_cow'] / 1024 / 1024 # Convert to MB
            total_cow += cow_mem
            total_no_cow += no_cow_mem
            
            diff = cow_mem - no_cow_mem
            if diff > 0:
                print(f"{bench}: CoW uses {diff:.2f} MB more memory ({diff/no_cow_mem*100:.2f}% more)")
            else:
                print(f"{bench}: No-CoW uses {abs(diff):.2f} MB more memory ({abs(diff)/cow_mem*100:.2f}% more)")
        
        # Overall average summary (in MB)
        print("\nOverall Memory Usage:")
        avg_cow = total_cow / len(avg_memory)
        min_cow = avg_memory['cow_mb'].min()
        max_cow = avg_memory['cow_mb'].max()
        avg_no_cow = total_no_cow / len(avg_memory)
        print(f"Average CoW Memory Usage: {avg_cow:.2f} MB (Min: {min_cow:.2f} MB, Max: {max_cow:.2f} MB)")
        print(f"Average No-CoW Memory Usage: {avg_no_cow:.2f} MB")
        
        diff = avg_cow - avg_no_cow
        if diff > 0:
            print(f"On average, CoW uses {diff:.2f} MB more memory ({diff/avg_no_cow*100:.2f}% more)")
        else:
            print(f"On average, No-CoW uses {abs(diff):.2f} MB more memory ({abs(diff)/avg_cow*100:.2f}% more)")

if __name__ == "__main__":
    main()
