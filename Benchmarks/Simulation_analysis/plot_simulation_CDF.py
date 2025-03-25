import matplotlib.pyplot as plt
import matplotlib as mpl
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

# Apply the requested settings
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
palette = sns.color_palette("deep", n_colors=6)
figwidth = 4.3
figheight = 2.2

TRACE_NAME = "default"

def find_section_boundaries(text):
    """Find the start indices of all variant sections in the text."""
    pattern = r'\*{13}\s*\w+\s*\*{16}'
    return [match.start() for match in re.finditer(pattern, text)]

def extract_section(text, start_idx, end_idx=None):
    """Extract a section of text between start_idx and end_idx."""
    if end_idx is None:
        return text[start_idx:]
    return text[start_idx:end_idx]

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
    
    if not (num_nodes_match and max_cache_match and soft_warm_pct_match and exec_slots_match and cache_util_match):
        print(f"Warning: Could not extract all configuration parameters for {variant}")
        return None
        
    num_nodes = int(num_nodes_match.group(1))
    max_cache = int(max_cache_match.group(1))
    soft_warm_pct = float(soft_warm_pct_match.group(1))
    exec_slots = int(exec_slots_match.group(1))
    cache_util = float(cache_util_match.group(1))
    
    # Extract delays
    delays = []
    delay_lists = re.findall(r'[^:]+:\s*(\[.*?\])', section_text)
    for delay_list in delay_lists:
        try:
            delay_values = eval(delay_list)
            delays.extend(delay_values)
        except Exception as e:
            print(f"Error parsing delay list for {variant}: {e}")
    
    return {
        'variant': variant,
        'num_nodes': num_nodes,
        'max_cache': max_cache,
        'soft_warm_pct': soft_warm_pct,
        'delays': delays,
        'exec_slots': exec_slots,
        'cache_util': cache_util
    }

def parallel_parse_section(args):
    """Parse a single section, suitable for Pool.map."""
    section_text, section_idx = args
    result = parse_section(section_text)
    if result:
        return result
    return None

def crop_pdf(input_path):
    """Use pdfcrop to crop the PDF file."""
    try:
        subprocess.run(['pdfcrop', input_path, input_path], check=True)
        print(f"Successfully cropped {input_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error cropping PDF {input_path}: {e}")
    except FileNotFoundError:
        print("pdfcrop command not found. Please install texlive-extra-utils package.")

def generate_cdf_plot(configs, output_path_base, title, ylim=(0, 1.05)):
    """Generate CDF plot for the given configurations and save to output_path."""
    plt.figure(figsize=(figwidth, figheight))
    
    # Use different line styles and colors for better distinction
    line_styles = ['-', '--', '-.', ':']
    colors = palette

    for i, config in enumerate(configs):
        variant = config['variant']
        num_nodes = config['num_nodes']
        max_cache = config['max_cache']
        soft_warm_pct = config['soft_warm_pct']
        delays = config['delays']
        exec_slots=config['exec_slots']
        cache_util=config['cache_util']
        
        if not delays:
            continue

        # Sort the data for CDF
        sorted_data = np.sort(delays)
        
        # Calculate the CDF values (y-axis)
        y_values = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
        
        # Create label with configuration details
        label = ""
        if variant == 'WALLET':
            label = f"{variant} - c:{max_cache}, w:{soft_warm_pct * 100}%, e:{exec_slots}, cu:{cache_util * 100}%"
        else: 
            label = f"{variant} - c:{max_cache}, e:{exec_slots}, cu:{cache_util * 100}%"
            
        
        # Plot the CDF with different line styles and colors
        style_idx = i % len(line_styles)
        color_idx = i % len(colors)
        plt.plot(sorted_data, y_values, linestyle=line_styles[style_idx], 
                 color=colors[color_idx], label=label, linewidth=1)
    
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xlabel('Scheduling Delay (seconds)', fontsize=TITLE_FONTSIZE)
    plt.ylabel('Cumulative Distribution', fontsize=TITLE_FONTSIZE)
    plt.title(title, fontsize=TITLE_FONTSIZE)
    plt.legend(loc='lower right', fontsize=LEGEND_FONTSIZE)
    
    # Set axes font sizes
    plt.xticks(fontsize=TICKS_FONTSIZE)
    plt.yticks(fontsize=TICKS_FONTSIZE)
    
    # Set y-axis to range from 0 to 1
    plt.ylim(*ylim)
    
    # Add a horizontal line at y=0.5 to visualize median
    plt.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_path_base), exist_ok=True)
    
    # Save as PDF
    pdf_path = f"{output_path_base}.pdf"
    plt.savefig(pdf_path)
    
    # Save as PNG with high DPI for quality
    png_path = f"{output_path_base}.png"
    plt.savefig(png_path, dpi=300)
    
    plt.close()
    
    # Crop the PDF
    if pdf_path.endswith('.pdf'):
        crop_pdf(pdf_path)
    
    return output_path_base

def parallel_plot_node_size(args):
    """Process a single node size plot for parallel execution."""
    configs, node_size, output_dir = args
    # Filter configs for this node size
    node_configs = [config for config in configs if config['num_nodes'] == node_size]
    
    # Generate plot
    output_path_base = os.path.join(output_dir, f"{TRACE_NAME}_node_size_{node_size}")
    title = f"Invocation Latency CDF - {node_size} Nodes"
    return generate_cdf_plot(node_configs, output_path_base, title)

def parallel_plot_filtered(args):
    """Process a single node size plot for parallel execution."""
    configs, node_size, exec_slots, output_dir = args
    # Filter configs for this node size
    node_configs = [config for config in configs 
                    if config['num_nodes'] == node_size and
                    config['exec_slots'] == exec_slots
                    ]
    
    # Generate plot
    output_path_base = os.path.join(output_dir, f"{TRACE_NAME}_filtered_n_{node_size}_e_{exec_slots}")
    title = f"Invocation Latency CDF - {node_size} Nodes"
    return generate_cdf_plot(node_configs, output_path_base, title)

def parallel_plot_node_cache(args):
    """Process a single node+cache size plot for parallel execution."""
    configs, node_size, cache_size, output_dir = args
    # Filter configs for this combination
    filtered_configs = [config for config in configs 
                       if config['num_nodes'] == node_size and config['max_cache'] == cache_size]
    
    if not filtered_configs:
        return None
        
    # Generate plot
    output_path_base = os.path.join(output_dir, f"{TRACE_NAME}_node_{node_size}_cache_{cache_size}")
    title = f"Invocation Latency CDF - {node_size} Nodes, {cache_size} Cache"
    return generate_cdf_plot(filtered_configs, output_path_base, title)

def process_by_node_size(configs, output_dir, pool):
    """Create plots grouped by node size in parallel."""
    # Group configs by node size
    node_sizes = set(config['num_nodes'] for config in configs)
    
    # Prepare arguments for parallel processing
    plot_args = [(configs, node_size, output_dir) for node_size in node_sizes]
    
    # Process plots in parallel
    results = pool.map(parallel_plot_node_size, plot_args)
    return results

def process_by_node_and_cache(configs, output_dir, pool):
    """Create plots grouped by node size and cache size combination in parallel."""
    # Get all unique node sizes and cache sizes
    node_sizes = set(config['num_nodes'] for config in configs)
    cache_sizes = set(config['max_cache'] for config in configs)
    
    # Prepare arguments for parallel processing
    plot_args = [(configs, node_size, cache_size, output_dir) 
                for node_size, cache_size in itertools.product(node_sizes, cache_sizes)]
    
    # Process plots in parallel
    results = pool.map(parallel_plot_node_cache, plot_args)
    # Filter out None results (combinations that didn't have data)
    return [r for r in results if r is not None]

def main():
    global TRACE_NAME
    
    start_time = time.time()
    
    # Create output directory
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
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
            # Generate overall CDF plot (not parallelized as it's just one plot)
            overall_output_path = os.path.join(output_dir, f"{TRACE_NAME}_overall_cdf")
            generate_cdf_plot(configs, overall_output_path, "Overall Invocation Latency CDF")
            
            # Generate plots by node size in parallel
            print("Generating node size plots in parallel...")
            node_plots = process_by_node_size(configs, output_dir, pool)
            print(f"Generated {len(node_plots)} node size plots")
            
            # Generate plots by node size + cache combination in parallel
            print("Generating node+cache combination plots in parallel...")
            combo_plots = process_by_node_and_cache(configs, output_dir, pool)
            print(f"Generated {len(combo_plots)} node+cache combination plots")

            # Generate plots by node size + cache combination in parallel
   #         print("Generating filtered plots in parallel...")
 #           parallel_plot_filtered((configs, 100, 2, output_dir))


        
        print(f"Plotting completed in {time.time() - plotting_start:.2f} seconds")
    else:
        print("No valid configurations found. Please check the input format.")
    
    print(f"Total execution time: {time.time() - start_time:.2f} seconds")
    print(f"Output files can be found in the '{output_dir}' directory")
    
    # Count the total number of generated files
    pdf_count = len([f for f in os.listdir(output_dir) if f.endswith('.pdf')])
    png_count = len([f for f in os.listdir(output_dir) if f.endswith('.png')])

    print(f"Total files generated: {pdf_count} PDFs and {png_count} PNGs")

if __name__ == "__main__":
    main()
