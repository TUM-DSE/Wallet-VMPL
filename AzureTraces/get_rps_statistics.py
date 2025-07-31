import sys
import pandas as pd
import numpy as np
import math

def analyze_request_timestamps(filename):
    # Read the CSV file
    df = pd.read_csv(filename)
    
    # Find the floor of the minimum timestamp
    #min_timestamp = math.floor(df['start_timestamp'].min())
    min_timestamp = 0
    
    # Find the ceiling of the maximum timestamp
    max_timestamp = math.ceil(df['start_timestamp'].max())
    
    # Calculate total number of seconds (inclusive of 0 to max)
#    total_seconds = int(max_timestamp - min_timestamp) + 1
    total_seconds = int(max_timestamp - min_timestamp) 
    
    # Create an array to count requests per second, initialized with zeros
    requests_per_second = [0] * total_seconds
    
    # Count requests for each second
    for timestamp in df['start_timestamp']:
        # Calculate the index by flooring the timestamp relative to min_timestamp
        second_index = int(math.floor(timestamp - min_timestamp))
        requests_per_second[second_index] += 1
    
    return requests_per_second

def print_statistics(requests_per_second):
    # Convert to numpy array for easier calculations
    rps_array = np.array(requests_per_second)
    
    print("Requests per Second Analysis:")
    print(f"Minimum requests: {rps_array.min()}")
    print(f"Maximum requests: {rps_array.max()}")
    print(f"Average requests: {rps_array.mean():.2f}")
    print(f"Standard Deviation: {rps_array.std():.2f}")

# Check if filename is provided as a command-line argument
if len(sys.argv) < 2:
    print("Usage: python get_rps_statistics.py <filename>")
    sys.exit(1)

# Get filename from command-line argument
filename = sys.argv[1]

# Analyze requests per second
requests_per_second = analyze_request_timestamps(filename)
print("\nRequests per Second Array:")
#print(requests_per_second)
print()
print_statistics(requests_per_second)
