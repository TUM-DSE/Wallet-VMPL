import matplotlib.pyplot as plt
import numpy as np
import re
import io
import sys

def parse_results(results_text):
    """Parse experimental results from text format."""
    # Split the text into variant sections
    pattern = r'(\*{13}\s*(\w+)\s*\*{16}[\s\S]*?)(?=\*{13}|\Z)'
    matches = re.findall(pattern, results_text)
    
    configs = []
    for full_section, variant in matches:
        # Extract configuration parameters
        num_nodes_match = re.search(r'num_nodes:\s*(\d+)', full_section)
        max_cache_match = re.search(r'max_functions_cached_per_node:\s*(\d+)', full_section)
        soft_warm_pct_match = re.search(r'percentage_soft_warm:\s*(\d+(?:\.\d+)*)', full_section)
        
        if not (num_nodes_match and max_cache_match and soft_warm_pct_match):
            print(f"Warning: Could not extract all configuration parameters for {variant}")
            continue
            
        num_nodes = int(num_nodes_match.group(1))
        max_cache = int(max_cache_match.group(1))
        soft_warm_pct = float(soft_warm_pct_match.group(1))
        
        # Extract delays
        delays = []
        delay_lists = re.findall(r'[^:]+:\s*(\[.*?\])', full_section)  # Modified line
        for delay_list in delay_lists:
            try:
                delay_values = eval(delay_list)
                delays.extend(delay_values)
            except Exception as e:
                print(f"Error parsing delay list for {variant}: {e}")
        
        configs.append({
            'variant': variant,
            'num_nodes': num_nodes,
            'max_cache': max_cache,
            'soft_warm_pct': soft_warm_pct,
            'delays': delays
        })
    
    return configs

def generate_cdf(configs):
    """Generate CDF plot for each configuration."""
    plt.figure(figsize=(12, 8))
    
    # Use different line styles and colors for better distinction
    line_styles = ['-', '--', '-.', ':']
    colors = ['blue', 'red', 'green', 'purple', 'orange', 'brown', 'pink', 'gray', 'olive', 'cyan']

    for i, config in enumerate(configs):
        variant = config['variant']
        num_nodes = config['num_nodes']
        max_cache = config['max_cache']
        soft_warm_pct = config['soft_warm_pct']
        delays = config['delays']
        # Remove zero values as they might skew the CDF
        delays = [d for d in delays]
        
        if not delays:
            continue
            
        # Sort the data for CDF
        sorted_data = np.sort(delays)
        print(len(sorted_data))
        # Calculate the CDF values (y-axis)
        y_values = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
        
        # Create label with configuration details
        label = f"{variant} - nodes:{num_nodes}, cache:{max_cache}, soft_warm:{soft_warm_pct}%"
        
        # Plot the CDF with different line styles and colors
        style_idx = i % len(line_styles)
        color_idx = i % len(colors)
        plt.plot(sorted_data, y_values, linestyle=line_styles[style_idx], 
                 color=colors[color_idx], label=label, linewidth=2)
    
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xlabel('Invocation Latency (seconds)', fontsize=12)
    plt.ylabel('Cumulative Distribution', fontsize=12)
    plt.title('CDF of Invocation Latency', fontsize=14)
    plt.legend(loc='lower right', fontsize=10)
    
    # Set y-axis to range from 0 to 1
    plt.ylim(0, 1.05)
    
    # Add a horizontal line at y=0.5 to visualize median
    plt.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig('invocation_latency_cdf.png', dpi=300)
    plt.show()

def main():
    # Check if file is provided as argument, otherwise read from stdin
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            results_text = f.read()
    else:
        results_text = sys.stdin.read()
    
    configs = parse_results(results_text)
    
    # Print summary of parsed configurations
    print("Parsed configurations:")
    for config in configs:
        print(f"- {config['variant']}: nodes={config['num_nodes']}, cache={config['max_cache']}, soft_warm={config['soft_warm_pct']}%, {len(config['delays'])} delay points")
    
    if configs:
        generate_cdf(configs)
    else:
        print("No valid configurations found. Please check the input format.")

if __name__ == "__main__":
    main()