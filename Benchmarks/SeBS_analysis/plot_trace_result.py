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

def analyze_trace_results(csv_path="trace_result.csv"):
    """
    Read trace_result.csv and show the average of each metric per benchmark and preallocation setting.
    
    Parameters:
    -----------
    csv_path : str
        Path to the CSV file containing trace results
    
    Returns:
    --------
    pd.DataFrame
        DataFrame containing average metrics per benchmark and preallocation setting
    """
    # Read the CSV file
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: {csv_path} not found.")
        return None
    except pd.errors.EmptyDataError:
        print(f"Error: {csv_path} is empty.")
        return None
    except Exception as e:
        print(f"Error reading {csv_path}: {e}")
        return None
    
    # Print available columns for debugging
    print("Available columns:", df.columns.tolist())
    
    # Check if required columns exist (for this specific format)
    if 'bench' not in df.columns:
        print("Error: Could not find 'bench' column which contains benchmark names.")
        return None
    
    # Group by benchmark and preallocation setting
    # This treats the combination as a hierarchical index
    metrics_cols = ['vmexit', 'vmgexit', 'pvalidate', 'page_fault', 'cow']
    avg_metrics = df.groupby(['bench', 'prealloc'])[metrics_cols].mean()
    
    return avg_metrics

def main():
    # Analyze trace results
    avg_metrics = analyze_trace_results()
    
    # Optionally plot results if data is available
    if avg_metrics is not None and not avg_metrics.empty:
        # Create output directory if it doesn't exist
        Path("output").mkdir(exist_ok=True)
        
        # Plot for each metric, comparing prealloc vs no_prealloc for each benchmark
        metrics_cols = avg_metrics.columns
        
        # Reset index to make 'bench' and 'prealloc' columns accessible
        plot_df = avg_metrics.reset_index()
        
        for metric in metrics_cols:
            plt.figure(figsize=(figwidth, figheight))
            
            # Use catplot to create grouped bar chart
            sns.barplot(x='bench', y=metric, hue='prealloc', data=plot_df)
            
            plt.title(f"Average {metric} by benchmark", fontsize=TITLE_FONTSIZE)
            plt.xlabel("Benchmark", fontsize=TICKS_FONTSIZE)
            plt.ylabel(metric, fontsize=TICKS_FONTSIZE)
            plt.xticks(rotation=45, ha='right', fontsize=TICKS_FONTSIZE)
            plt.yticks(fontsize=TICKS_FONTSIZE)
            plt.legend(fontsize=LEGEND_FONTSIZE)
            plt.tight_layout()
            
            # Save in both PDF and PNG formats
            plt.savefig(f"output/avg_{metric}_by_benchmark.pdf")
            plt.savefig(f"output/avg_{metric}_by_benchmark.png", dpi=300)
            plt.close()
        
        # Print summary of average metrics at the end
        print("\n=== Summary of Average Metrics by Benchmark and Preallocation ===")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 120)
        pd.set_option('display.float_format', '{:.4g}'.format)
        print(avg_metrics)
        
        # Print more detailed breakdown
        print("\nDetailed metrics by benchmark:")
        for bench, group in avg_metrics.groupby(level=0):
            print(f"\n{bench}:")
            for prealloc_setting, row in group.groupby(level=1):
                print(f"  {prealloc_setting}:")
                for metric in row.columns:
                    value = row[metric].values[0]
                    print(f"    {metric}: {value:.4g}")

if __name__ == "__main__":
    main()
