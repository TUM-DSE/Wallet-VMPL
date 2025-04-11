import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np
import re
import io
import sys
import os
import seaborn as sns
from multiprocessing import Pool, cpu_count, Lock
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

# Create a global lock for synchronized printing
print_lock = Lock()

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
            print(f"Error parsing {section_name} list for {variant}: {e}")
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
    delays =  extract_indented_section_values(section_text, "Delays")
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

def setup_axis_formatters(ax):
    """Set up the log axis with powers of 10 formatting for both x and y axes."""
    # Create a custom formatter for powers of 10
    class PowersOf10Formatter(ScalarFormatter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.set_scientific(False)
            
        def __call__(self, x, pos=None):
          # For zero, just return 0
          if x == 0:
              return '0'
              
          # For large numbers, use scientific notation
          if abs(x) >= 1000:
              power = int(np.log10(abs(x)))
              base = x / (10**power)
              
              # If it's an exact power of 10
              if abs(base - 1.0) < 1e-10:
                  return f'$10^{power}$'
              # If it's a simple coefficient times a power of 10 (like 2×10^3, 5×10^4, etc.)
              elif abs(base) == int(abs(base)) or abs(abs(base) - round(abs(base), 1)) < 1e-10:
                  if abs(base) == int(abs(base)):
                      coefficient = int(abs(base))
                  else:
                      coefficient = round(abs(base), 1)
                      
                  # Handle negative numbers
                  sign = '-' if x < 0 else ''
                  
                  return f'${sign}{coefficient}\\times10^{{{power}}}$'
              else:
                  # For other values, use regular formatting
                  return f'{x:.0f}'
          else:
              # For smaller numbers, use regular formatting
              # If it's a whole number, show no decimal places
              if x == int(x):
                  return f'{int(x)}'
              # Otherwise show one decimal place
              else:
                  return f'{x:.1f}'

    # Apply the formatter for both axes
    x_formatter = PowersOf10Formatter()
    y_formatter = PowersOf10Formatter()
    
    if ax.get_xscale() == 'log':
        # For log scale, use LogLocator
        x_locator = LogLocator(base=10)
        ax.xaxis.set_major_locator(x_locator)
        ax.xaxis.set_major_formatter(x_formatter)
        
        # Add minor grid lines for log scale
        ax.grid(True, which='major', alpha=0.5)
        ax.grid(False, which='minor')
    else:
        ax.xaxis.set_major_formatter(x_formatter)
    
    # Apply formatter to y-axis as well
    if ax.get_yscale() == 'log':
        y_locator = LogLocator(base=10)
        ax.yaxis.set_major_locator(y_locator)
    
    ax.yaxis.set_major_formatter(y_formatter)

def plot_percentile_delay_latency(configs, output_dir, use_log_scale=False):
    """
    Create a plot of P99 and P50 delay latency across different node sizes for multiple variants.

    Args:
        configs (list): List of configuration dictionaries
        output_dir (str): Directory to save output plots

    Returns:
        str: Path to the generated plot
    """
    # Create standardized plot using config
    fig, ax = create_standardized_plot(ax_height = 0.95, top_margin = 0.2, bottom_margin = 0.3)

    # Set x-axis to log scale if requested
    if use_log_scale:
        ax.set_xscale('log')
        
    # Use different line styles and markers for better distinction
    line_styles = ['-', '--', '-.', ':']
    markers = ['o', 's', '^', 'D', 'v']
    colors = PALETTE_REGULAR

    # Get unique node sizes
    unique_node_sizes = sorted(set(config['num_nodes'] for config in configs))

    # Prepare to store plot data
    plot_data = {
        'P99': {},
        'P50': {}
    }

    # Sort configs according to the order in LABEL_MAPPINGS_SIMULATIONS_EVALUATION
    # We can create a sorting key based on the position of each variant in the dictionary
    variant_order = {variant: i for i, variant in enumerate(LABEL_MAPPINGS_SIMULATIONS_EVALUATION.keys())}
    sorted_variants = sorted(
        set(config['variant'] for config in configs),
        key=lambda x: variant_order.get(x, float('inf'))
    )
    
    # Iterate through each variant
    for variant in sorted_variants:
        # Filter configs for this variant
        variant_configs = [config for config in configs if config['variant'] == variant]

        # Prepare data for this variant
        variant_p99_delays = []
        variant_p50_delays = []
        variant_node_sizes = []

        for node_size in unique_node_sizes:
            # Find configurations for this variant and node size
            node_configs = [config for config in variant_configs if config['num_nodes'] == node_size]

            if node_configs:
                # Calculate P99 and P50 delays for these configurations
                p99_delays = [np.percentile(config['delays'], 99) for config in node_configs if config['delays']]
                p50_delays = [np.percentile(config['delays'], 50) for config in node_configs if config['delays']]

                if p99_delays and p50_delays:
                    # Use the median percentile if multiple configurations exist
                    median_p99_delay = np.median(p99_delays)
                    median_p50_delay = np.median(p50_delays)

                    variant_p99_delays.append(median_p99_delay)
                    variant_p50_delays.append(median_p50_delay)
                    variant_node_sizes.append(node_size)

        # Store data for plotting
        plot_data['P99'][variant] = {
            'node_sizes': variant_node_sizes,
            'delays': variant_p99_delays
        }
        plot_data['P50'][variant] = {
            'node_sizes': variant_node_sizes,
            'delays': variant_p50_delays
        }

    # Plot P99 and P50 for each variant
    percentiles = ['P99', 'P50']
    for percentile_idx, percentile in enumerate(percentiles):
        for variant_idx, variant in enumerate(sorted_variants):
            # Skip if this variant doesn't have data for this percentile
            if variant not in plot_data[percentile]:
                continue
              
            # Get data for this variant and percentile
            node_sizes = plot_data[percentile][variant]['node_sizes']
            delays = plot_data[percentile][variant]['delays']

            # Skip if no data
            if not node_sizes or not delays:
                continue
              
            # Select style and color
            style_idx = variant_idx % len(line_styles)
            color_idx = variant_idx % len(colors)
            marker_idx = variant_idx % len(markers)

            # Adjust line style and marker for different percentiles
            linestyle = line_styles[style_idx]
            marker = markers[marker_idx]
            color = colors[color_idx]

            # Modify style for P50 to distinguish from P99
            if percentile == 'P50':
                linestyle = ':' if linestyle == '-' else '-.'
                marker = 'x'

            # Map the variant name if it exists in mapping dict
            display_variant = LABEL_MAPPINGS_SIMULATIONS_EVALUATION[variant]
            
            # Plot with a label that includes the percentile
            plt.plot(node_sizes, delays,
                     marker=marker,
                     markersize=MARKER_SIZE,
                     linestyle=linestyle,
                     color=color,
                     label=f'{display_variant}-{percentile.lower()}',
                     linewidth=1)

    # You can explicitly set the tick positions and labels
    tick_positions = np.linspace(min(unique_node_sizes), max(unique_node_sizes), len(unique_node_sizes))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([str(size) for size in unique_node_sizes])
        
    title = "Invocation Latency Percentiles"
    x_label = "Number of nodes"
    y_label = "Invocation latency (ms)"
    # Apply consistent styling from the configuration
    apply_consistent_style(ax, 
                       title=title,
                       xlabel=x_label,
                       ylabel=y_label)

    # # Set up decimal formatting for log scale
    # if use_log_scale:
    #     setup_log_formatter(ax)
    # Apply the improved axis formatter
    setup_axis_formatters(ax)
    
    # bring y-label a bit closer to fit
    ax.yaxis.labelpad = 1.5
    
    # Add a horizontal line at y=0.5 to visualize median
    ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    
    # Add legend with standardized position and style
    legend = ax.legend(loc='center', bbox_to_anchor=(0.52, 0.75), framealpha=0.3, edgecolor='black', borderaxespad=0., fontsize=LEGEND_FONTSIZE, 
                        frameon=True, ncols=2, columnspacing=0.3, labelspacing=0.2, borderpad=0.1, handletextpad=0.3)
    legend.get_frame().set_edgecolor('black')
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(f'{output_dir}/pdf'), exist_ok=True)
    os.makedirs(os.path.dirname(f'{output_dir}/png'), exist_ok=True)
    
    # Create file suffix based on plot options
    suffix = "_log" if use_log_scale else ""
    output_name = f"{TRACE_NAME}_percentile_delay_nodes"
    
    # Save as PDF
    pdf_path = f"{output_dir}/pdf/{output_name}{suffix}.pdf"
    plt.savefig(pdf_path, dpi=300, bbox_inches=None)
    
    # Save as PNG with high DPI for quality
    png_path = f"{output_dir}/png/{output_name}{suffix}.png"
    plt.savefig(png_path, dpi=300, bbox_inches=None)

    plt.close()


  # Add summary table at the end
    print("\nLatency Summary Table (milliseconds):")
    print("=" * 120)
    
    # Create header with node sizes
    header = f"{'Variant':<15}"
    for node_size in unique_node_sizes:
        header += f" | {node_size:^9} nodes"
    print(header)
    print("-" * 120)

    # Print P50 values first
    for variant in sorted_variants:
        if variant in plot_data['P50']:
            variant_display = LABEL_MAPPINGS_SIMULATIONS_EVALUATION[variant]
            line = f"{variant_display} P50"
            line = f"{line:<15}"
            for node_size in unique_node_sizes:
                # Find this node size in the variant's data
                if node_size in plot_data['P50'][variant]['node_sizes']:
                    idx = plot_data['P50'][variant]['node_sizes'].index(node_size)
                    value = plot_data['P50'][variant]['delays'][idx]
                    # Format value to be right-aligned with 2 decimal places
                    formatted_value = f"{value:.2f}".rjust(15)
                    line += f" | {formatted_value}"
                else:
                    line += f" | {'N/A':>15}"
            print(line)

    # Print P99 values
    for variant in sorted_variants:
        if variant in plot_data['P99']:
            variant_display = LABEL_MAPPINGS_SIMULATIONS_EVALUATION[variant]
            line = f"{variant_display} P99"
            line = f"{line:<15}"
            for node_size in unique_node_sizes:
                # Find this node size in the variant's data
                if node_size in plot_data['P99'][variant]['node_sizes']:
                    idx = plot_data['P99'][variant]['node_sizes'].index(node_size)
                    value = plot_data['P99'][variant]['delays'][idx]
                    # Format value to be right-aligned with 2 decimal places
                    formatted_value = f"{value:.2f}".rjust(15)
                    line += f" | {formatted_value}"
                else:
                    line += f" | {'N/A':>15}"
            print(line)
    
    print("=" * 120)

    return pdf_path

def generate_cdf_plot(configs, output_dir, output_name, title,  value_type, ylim=(0, 1.05), use_log_scale=False):
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

    # Sort configs according to the order in LABEL_MAPPINGS_SIMULATIONS_EVALUATION
    # We can create a sorting key based on the position of each variant in the dictionary
    variant_order = {variant: i for i, variant in enumerate(LABEL_MAPPINGS_SIMULATIONS_EVALUATION.keys())}
    sorted_configs = sorted(configs, key=lambda x: variant_order.get(x['variant'], float('inf')))

    for i, config in enumerate(sorted_configs):
        variant = config['variant']
        num_nodes = config['num_nodes']
        max_cache = config['max_cache']
        soft_warm_pct = config['soft_warm_pct']
        #delays = config['delays']
        #slowdowns = config['slowdowns']
        values = config[value_type]
        exec_slots=config['exec_slots']
        cache_util=config['cache_util']
        cold_rate=config['cold_rate']
        
        if not values:
            continue

        # Sort the data for CDF
        sorted_data = np.sort(values)
        max_x_value = max(max_x_value, sorted_data[-1])
        
        # Calculate the CDF values (y-axis)
        y_values = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
        
        # Map the variant name if it exists in mapping dict
        display_variant = LABEL_MAPPINGS_SIMULATIONS_EVALUATION[variant]
        
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
        x_label = 'Invocation delay (ms)'
    elif value_type == 'slowdowns':
        x_label = 'Per-function slowdown'

    # Apply consistent styling from the configuration
    apply_consistent_style(ax, 
                       title=title,
                       xlabel=x_label,
                       ylabel=y_label)
    
    # # Set up decimal formatting for log scale
    # if use_log_scale:
    #     setup_log_formatter(ax)
    # Apply the improved axis formatter
    setup_axis_formatters(ax)
    
    # Set y-axis to range from 0 to 1
    plt.ylim(*ylim)

    # Add a horizontal line at y=0.5 to visualize median
    plt.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    
    # Add legend with standardized position and style
    legend = ax.legend(loc='center', bbox_to_anchor=(0.65, 0.18), framealpha=0.3, edgecolor='black', borderaxespad=0., fontsize=LEGEND_FONTSIZE, 
                        frameon=True, ncols=2, columnspacing=0.3, labelspacing=0.2, borderpad=0.1, handletextpad=0.3)
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
    
    # Print summary of P50, P90, P99 with lock to prevent mixed output
    with print_lock:
        print(f"\nLatency Summary for {title}: {x_label}:")
        print("=" * 120)

        unit = "(ms)" if value_type == "delays" else "    "
        
        # Create header
        header = f"{'Variant':<15} | {'P50 '+unit:>15} | {'P90 '+unit:>15} | {'P99 '+unit:>15}"
        print(header)
        print("-" * 120)
        
        # Print percentiles for each variant
        for config in sorted_configs:
            variant = config['variant']
            display_variant = LABEL_MAPPINGS_SIMULATIONS_EVALUATION[variant]
            
            if value_type in config and config[value_type]:
                values = np.array(config[value_type])
                p50 = np.percentile(values, 50)
                p90 = np.percentile(values, 90)
                p99 = np.percentile(values, 99)
                
                line = f"{display_variant:<15} | {p50:15.2f} | {p90:15.2f} | {p99:15.2f}"
                print(line)
        
        print("=" * 120)
    
    return f'{output_dir}/pdf/{output_name}'

def parallel_plot_node_size(args):
    """Process a single node size plot for parallel execution."""
    configs, node_size, output_dir, value_type = args
    # Filter configs for this node size
    node_configs = [config for config in configs if config['num_nodes'] == node_size]
    
    # Generate plot
    if (value_type == "delays"): 
      title = f"Invocation Latency CDF ({node_size} Nodes)"
    elif (value_type == "slowdowns"):
      title = f"Per function slowdown CDF ({node_size} Nodes)"
    linear_plot = generate_cdf_plot(node_configs, output_dir, f"{TRACE_NAME}_node_size_{node_size}_{value_type}", title, value_type)
    log_plot    = generate_cdf_plot(node_configs, output_dir, f"{TRACE_NAME}_node_size_{node_size}_{value_type}", title, value_type, use_log_scale=True)
    return [linear_plot, log_plot]

def process_by_node_size(configs, output_dir, pool, value_type):
    """Create plots grouped by node size in parallel."""
    # Group configs by node size
    node_sizes = set(config['num_nodes'] for config in configs)
    
    # Prepare arguments for parallel processing
    plot_args = [(configs, node_size, output_dir, value_type) for node_size in node_sizes]
    
    # Process plots in parallel
    results = pool.map(parallel_plot_node_size, plot_args)
    return results

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
    else:
        print("Please provide a file as a first argument")
        exit()
    TRACE_NAME = sys.argv[1].split("/")[-1].split(".txt")[0]
    print(f"File read completed in {time.time() - start_time:.2f} seconds")
    chunking_start = time.time()
    
    # Determine number of CPU cores to use
    num_cores = cpu_count()
    print(f"Using {num_cores} CPU cores for parallel processing")
    
    # Find all section boundaries in parallel
    print("Finding section boundaries...")
    boundaries = find_section_boundaries(results_text)
    print(f"Found {len(boundaries)} sections in {time.time() - chunking_start:.2f} seconds")
    
    # Prepare sections for parallel parsing
    sections = []
    for i, start_idx in enumerate(boundaries):
        end_idx = boundaries[i+1] if i+1 < len(boundaries) else None
        section_text = extract_section(results_text, start_idx, end_idx)
        sections.append((section_text, i))
    
    print(f"Section extraction completed in {time.time() - chunking_start:.2f} seconds")
    parsing_start = time.time()
    
    # Parse sections in parallel
    print(f"Parsing {len(sections)} sections in parallel...")
    with Pool(processes=num_cores) as pool:
        configs = pool.map(parallel_parse_section, sections)
    
    # Filter out None results
    configs = [config for config in configs if config]
    
    print(f"Parsing completed in {time.time() - parsing_start:.2f} seconds")
    
    # Print summary of parsed configurations
    print("\nParsed configurations:")
    for config in configs:
        print(f"- {config['variant']}: nodes={config['num_nodes']}, cache={config['max_cache']}, "
              f"soft_warm={config['soft_warm_pct']}%, {len(config['delays'])} delay points")
    
    plotting_start = time.time()
    if configs:
        with Pool(processes=num_cores) as pool:
            # Generate P99
            plot_percentile_delay_latency(configs, output_dir)
            
            # Generate plots by node size in parallel
            print("Generating node size plots in parallel...")
            node_plots = process_by_node_size(configs, output_dir, pool, "delays")
            node_plots = process_by_node_size(configs, output_dir, pool, "slowdowns")
            print(f"Generated {len(node_plots)} node size plots")
        
        print(f"Plotting completed in {time.time() - plotting_start:.2f} seconds")
    else:
        print("No valid configurations found. Please check the input format.")
    
    print(f"Total execution time: {time.time() - start_time:.2f} seconds")
    print(f"Output files can be found in the '{output_dir}' directory")
    
    # Count the total number of generated files
    pdf_count = len([f for f in os.listdir(f'{output_dir}/pdf') if f.endswith('.pdf')])
    png_count = len([f for f in os.listdir(f'{output_dir}/png') if f.endswith('.png')])

    print(f"Total files generated: {pdf_count} PDFs and {png_count} PNGs")

if __name__ == "__main__":
    main()
