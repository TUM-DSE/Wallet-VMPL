#!/usr/bin/env python3

import matplotlib.pyplot as plt
import numpy as np
import re
import io
import sys
import os
import seaborn as sns
from multiprocessing import Pool, cpu_count
from functools import partial
import itertools
from pathlib import Path
from matplotlib.backends.backend_pdf import PdfPages
import subprocess
import tempfile
import time
from matplotlib.ticker import ScalarFormatter, LogFormatter, LogLocator

# Import centralized plotting configuration
import sys
sys.path.append('..')
from motivation_plotting_config import *

# Define global variables
TRACE_NAME = "default"

def split_text_by_indentation(text):
    """
    Split a text into sections based on top-level indented blocks.
    
    Args:
        text (str): The input text to be split
    
    Returns:
        dict: A dictionary where keys are section names and values are multiline strings
    """
    # Split the text into lines and remove empty lines
    lines = [line for line in text.split('\n') if line.strip()]
    
    sections = {}
    current_section = None
    current_section_lines = []
    
    for line in lines:
        # Check if this is a section header (ends with ':' and has no leading spaces)
        if line.strip().endswith(':') and not line.startswith(' '):
            # If we were building a previous section, save it
            if current_section is not None:
                sections[current_section] = '\n'.join(current_section_lines)
            
            current_section = line.strip()[:-1]
            current_section_lines = []
        
        # If it's an indented line and we have a current section, add it to that section
        elif line.startswith('    ') and current_section is not None:
            current_section_lines.append(line)
    
    # Save the last section
    if current_section is not None:
        sections[current_section] = '\n'.join(current_section_lines)
    
    return sections

def get_indented_section(text, section_name):
    """
    Retrieve a specific section from the text.
    
    Args:
        text (str): The input text
        section_name (str): The name of the section to retrieve
    
    Returns:
        str: Multiline string of the specified section
    """
    sections = split_text_by_indentation(text)
    return sections.get(section_name, '')

def find_section_boundaries(text):
    """Find the start indices of all variant sections in the text."""
    pattern = r'\*{13}\s*\w+\s*\*{16}'
    return [match.start() for match in re.finditer(pattern, text)]

def extract_section(text, start_idx, end_idx=None):
    """Extract a section of text between start_idx and end_idx."""
    if end_idx is None:
        return text[start_idx:]
    return text[start_idx:end_idx]

def extract_indented_section_values(text, section_name):
    values = []
    values_lists = re.findall(r'[^:]+:\s*(\[.*?\])', get_indented_section(text, section_name))
    for value_list in values_lists:
        try:
            partial_values = eval(value_list)
            values.extend(partial_values)
        except Exception as e:
            print(f"Error parsing {section_name} list: {e}")
    return values

def parse_section(section_text):
    """Parse a single variant section."""
    # Extract variant name
    variant_match = re.search(r'\*{13}\s*(\w+)\s*\*{16}', section_text)
    if not variant_match:
        return None
    
    variant = variant_match.group(1)
    
    # Extract configuration parameters
    num_nodes_match = re.search(r'num_nodes:\s*(\d+)', section_text)
    max_cache_match = re.search(r'max_functions_cached_per_node:\s*(\d+)', section_text)
    soft_warm_pct_match = re.search(r'percentage_soft_warm:\s*(\d+(?:\.\d+)*)', section_text)
    exec_slots_match = re.search(r'max_executions_slots:\s*(\d+)', section_text)
    cache_util_match = re.search(r'(?<=Max cache utilization:\s)(\d+(?:\.\d+)*)', section_text)
    cold_rate_match = re.search(r'(?<=Cold boot rate:\s)(\d+(?:\.\d+)*)', section_text)
    
    if not (num_nodes_match and max_cache_match and soft_warm_pct_match and exec_slots_match and cache_util_match and cold_rate_match):
        print(f"Warning: Could not extract all configuration parameters for {variant}")
        return None
        
    num_nodes = int(num_nodes_match.group(1))
    max_cache = int(max_cache_match.group(1))
    soft_warm_pct = float(soft_warm_pct_match.group(1))
    exec_slots = int(exec_slots_match.group(1))
    cache_util = float(cache_util_match.group(1))
    cold_rate = float(cold_rate_match.group(1))
    
    sections = split_text_by_indentation(section_text)

    # Extract delays
    delays = extract_indented_section_values(section_text, "Delays")
    delays = [delay * 1000 for delay in delays]  # Convert to milliseconds

    # Extract slowdowns
    slowdowns = extract_indented_section_values(section_text, "Slowdowns")

    return {
        'variant': variant,
        'num_nodes': num_nodes,
        'max_cache': max_cache,
        'soft_warm_pct': soft_warm_pct,
        'delays': delays,
        'exec_slots': exec_slots,
        'cache_util': cache_util,
        'slowdowns': slowdowns,
        'cold_rate': cold_rate
    }

def parallel_parse_section(args):
    """Parse a single section, suitable for Pool.map."""
    section_text, section_idx = args
    result = parse_section(section_text)
    if result:
        return result
    return None

def setup_log_formatter(ax):
    """Set up the log axis with decimal formatting."""
    if ax.get_xscale() == 'log':
        # Create a formatter that will use regular decimals instead of scientific notation
        formatter = ScalarFormatter()
        formatter.set_scientific(False)

        # Create custom log locator for more control over tick positions
        locator = LogLocator(base=10)

        # Apply formatter and locator to the x-axis
        ax.xaxis.set_major_formatter(formatter)
        ax.xaxis.set_major_locator(locator)

        # Ensure grid aligns with major ticks
        ax.grid(True, which='major', alpha=0.5)
        ax.grid(False, which='minor')

def generate_cdf_plot(configs, output_dir, output_name, title, value_type, ylim=(0, 1.05), use_log_scale=False):
    """Generate CDF plot for the given configurations and save to output_path."""
    # Create standardized plot using config
    fig, ax = create_standardized_plot(ax_height = 0.95, top_margin = 0.2, bottom_margin = 0.3)
    
    # Set x-axis to log scale if requested
    if use_log_scale:
        ax.set_xscale('log')

    # Use different line styles and colors for better distinction
    line_styles = ['-', '--', '-.', ':']
    colors = PALETTE_REGULAR

    # Keep track of max x value for setting plot limits properly
    max_x_value = 0

    # Sort configs according to the order in LABEL_MAPPINGS_SIMULATIONS_MOTIVATION
    # We can create a sorting key based on the position of each variant in the dictionary
    variant_order = {variant: i for i, variant in enumerate(LABEL_MAPPINGS_SIMULATIONS_MOTIVATION.keys())}
    sorted_configs = sorted(configs, key=lambda x: variant_order.get(x['variant'], float('inf')))
    
    for i, config in enumerate(sorted_configs):
        variant = config['variant']
        num_nodes = config['num_nodes']
        max_cache = config['max_cache']
        soft_warm_pct = config['soft_warm_pct']
        values = config[value_type]
        exec_slots = config['exec_slots']
        cache_util = config['cache_util']
        cold_rate = config['cold_rate']
        
        if not values:
            continue

        # Sort the data for CDF
        sorted_data = np.sort(values)
        max_x_value = max(max_x_value, sorted_data[-1])
        
        # Calculate the CDF values (y-axis)
        y_values = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
        
        # Map the variant name if it exists in mapping dict
        display_variant = LABEL_MAPPINGS_SIMULATIONS_MOTIVATION[variant]
        
        # Create label with configuration details
        label = ""
        if variant == 'WALLET':
            # label = f"{display_variant}: c:{max_cache}, w:{soft_warm_pct * 100}%, e:{exec_slots}, cu:{cache_util * 100:.1f}%, cr:{cold_rate * 100:.1f}%"
            print(f"{display_variant}: c:{max_cache}, w:{soft_warm_pct * 100}%, e:{exec_slots}, cu:{cache_util * 100:.1f}%, cr:{cold_rate * 100:.1f}%")
            label = f"{display_variant}"
        else: 
            # label = f"{display_variant}: c:{max_cache}, e:{exec_slots}, cu:{cache_util * 100:.1f}%, cr:{cold_rate * 100:.1f}%"
            print(f"{display_variant}: c:{max_cache}, e:{exec_slots}, cu:{cache_util * 100:.1f}%, cr:{cold_rate * 100:.1f}%")
            label = f"{display_variant}"
        
        # Plot the CDF with different line styles and colors
        style_idx = i % len(line_styles)
        color_idx = i % len(colors)

        # Main plot
        ax.plot(sorted_data, y_values, 
                linestyle=line_styles[style_idx], 
                color=colors[color_idx], 
                label=label, 
                linewidth=LINE_WIDTH)
    
    # Determine appropriate x-label based on value_type
    x_label = "Value"
    y_label = "Cumulative distribution"
    if value_type == 'delays':
        x_label = 'Scheduling delay (ms)'
    elif value_type == 'slowdowns':
        x_label = 'Per-function slowdown'

    # Apply consistent styling from the configuration
    apply_consistent_style(ax, 
                       title=title,
                       xlabel=x_label,
                       ylabel=y_label)
    
    # Set up decimal formatting for log scale
    if use_log_scale:
        setup_log_formatter(ax)

    # Set y-axis to range from 0 to 1
    ax.set_ylim(*ylim)

    # Add a horizontal line at y=0.5 to visualize median
    ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    
    # Add legend with standardized position and style
    legend = ax.legend(loc='center', bbox_to_anchor=(0.7, 0.35), edgecolor='black', borderaxespad=0., fontsize=LEGEND_FONTSIZE, 
                        frameon=True, ncols=1)
    legend.get_frame().set_edgecolor('black')
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(f'{output_dir}/pdf'), exist_ok=True)
    os.makedirs(os.path.dirname(f'{output_dir}/png'), exist_ok=True)
    
    # Create file suffix based on plot options
    suffix = "_log" if use_log_scale else ""

    # Save as PDF
    pdf_path = f"{output_dir}/pdf/{output_name}{suffix}.pdf"
    plt.savefig(pdf_path, dpi=300, bbox_inches=None)
    
    # Save as PNG with high DPI for quality
    png_path = f"{output_dir}/png/{output_name}{suffix}.png"
    plt.savefig(png_path, dpi=300, bbox_inches=None)
    
    plt.close()
    
    return f'{output_dir}/pdf/{output_name}'

def parallel_plot_node_size(args):
    """Process a single node size plot for parallel execution."""
    configs, node_size, output_dir, value_type = args
    # Filter configs for this node size
    node_configs = [config for config in configs if config['num_nodes'] == node_size]
    
    # Skip if no configs match
    if not node_configs:
        return None
    
    # Generate different plot versions with the same data
    title = f"(a) Invocation Latency CDF ({node_size} Nodes)"
    base_output_name = f"{TRACE_NAME}_node_size_{node_size}_{value_type}"
    
    # Generate original plot
    generate_cdf_plot(node_configs, output_dir, base_output_name, title, value_type)

    # Generate log scale plot
    generate_cdf_plot(node_configs, output_dir, base_output_name, title, value_type, use_log_scale=True)

    return output_dir + "/pdf/" + base_output_name

def process_by_node_size(configs, output_dir, pool, value_type):
    """Create plots grouped by node size in parallel."""
    # Group configs by node size
    node_sizes = set(config['num_nodes'] for config in configs)
    
    # Prepare arguments for parallel processing
    plot_args = [(configs, node_size, output_dir, value_type) for node_size in node_sizes]
    
    # Process plots in parallel
    results = pool.map(parallel_plot_node_size, plot_args)
    # Filter out None results
    return [r for r in results if r is not None]

def main():
    global TRACE_NAME
    
    start_time = time.time()
    
    # Create output directory
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(f'{output_dir}/pdf', exist_ok=True)
    os.makedirs(f'{output_dir}/png', exist_ok=True)
    
    # Check if file is provided as argument, otherwise read from stdin
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            results_text = f.read()
        TRACE_NAME = Path(sys.argv[1]).stem
    else:
        print("Please provide a file as a first argument")
        exit()
    TRACE_NAME = sys.argv[1].split("/")[-1].split(".txt")[0]
    print(f"File read completed in {time.time() - start_time:.2f} s")
    chunking_start = time.time()
    
    # Determine number of CPU cores to use
    num_cores = cpu_count()
    print(f"Using {num_cores} CPU cores for parallel processing")
    
    # Find all section boundaries in parallel
    print("Finding section boundaries...")
    boundaries = find_section_boundaries(results_text)
    print(f"Found {len(boundaries)} sections in {time.time() - chunking_start:.2f} s")
    
    # Prepare sections for parallel parsing
    sections = []
    for i, start_idx in enumerate(boundaries):
        end_idx = boundaries[i+1] if i+1 < len(boundaries) else None
        section_text = extract_section(results_text, start_idx, end_idx)
        sections.append((section_text, i))
    
    print(f"Section extraction completed in {time.time() - chunking_start:.2f} s")
    parsing_start = time.time()
    
    # Parse sections in parallel
    print(f"Parsing {len(sections)} sections in parallel...")
    with Pool(processes=num_cores) as pool:
        configs = pool.map(parallel_parse_section, sections)
    
    # Filter out None results
    configs = [config for config in configs if config]
    
    print(f"Parsing completed in {time.time() - parsing_start:.2f} s")
    
    # Print summary of parsed configurations
    print("\nParsed configurations:")
    for config in configs:
        print(f"- {config['variant']}: nodes={config['num_nodes']}, cache={config['max_cache']}, "
              f"soft_warm={config['soft_warm_pct']}%, {len(config['delays'])} delay points")
    
    plotting_start = time.time()
    if configs:
        with Pool(processes=num_cores) as pool:      
            # Generate plots by node size in parallel
            print("Generating node size plots in parallel...")
            node_delay_plots = process_by_node_size(configs, output_dir, pool, "delays")
            print(f"Generated {len(node_delay_plots)} node size delay plots")
            
            node_slowdown_plots = process_by_node_size(configs, output_dir, pool, "slowdowns")
            print(f"Generated {len(node_slowdown_plots)} node size slowdown plots")
        
        print(f"Plotting completed in {time.time() - plotting_start:.2f} s")
    else:
        print("No valid configurations found. Please check the input format.")
    
    print(f"Total execution time: {time.time() - start_time:.2f} s")
    print(f"Output files can be found in the '{output_dir}' directory")
    
    # Count the total number of generated files
    pdf_count = len([f for f in os.listdir(f'{output_dir}/pdf') if f.endswith('.pdf')])
    png_count = len([f for f in os.listdir(f'{output_dir}/png') if f.endswith('.png')])

    print(f"Total files generated: {pdf_count} PDFs and {png_count} PNGs")

if __name__ == "__main__":
    main()