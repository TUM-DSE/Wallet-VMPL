import pandas as pd
import numpy as np
import argparse
from sklearn.neighbors import KernelDensity
from sklearn.preprocessing import MinMaxScaler
from scipy.stats import gaussian_kde

def load_and_preprocess_data(filename):
    """
    Load data from a CSV file and preprocess it by converting specific columns to float
    and dropping rows with NaN or non-positive values.
    """
    data = pd.read_csv(filename, names=['app', 'func', 'end_timestamp', 'duration'])
    data['end_timestamp'] = pd.to_numeric(data['end_timestamp'], errors='coerce')
    data['duration'] = pd.to_numeric(data['duration'], errors='coerce')
    data = data[(data['end_timestamp'] >= 0) & (data['duration'] > 0)]
    data['event_id'] = data['app'] + "_" + data['func']
    return data

def scale_data(data):
    """
    Scale the 'end_timestamp' and 'duration' columns of the data.
    """
    timestamp_scaler = MinMaxScaler()
    duration_scaler = MinMaxScaler()
    data['scaled_end_timestamp'] = timestamp_scaler.fit_transform(data[['end_timestamp']])
    data['scaled_duration'] = duration_scaler.fit_transform(data[['duration']])
    return data, timestamp_scaler, duration_scaler

def fit_kde_estimators(data, min_kde=1):
    """
    Fit Kernel Density Estimators for 'end_timestamp' and 'duration'.
    """
    kdes_timestamp = {}
    kdes_duration = {}
    unique_identifiers = data['event_id'].unique()

    for identifier in unique_identifiers:
        subset_timestamp = data[data['event_id'] == identifier]['scaled_end_timestamp']
        subset_duration = data[data['event_id'] == identifier]['scaled_duration']

        if len(subset_timestamp) >= min_kde:
            kde_timestamp, bandwidth_end_timestamp = fit_kde(subset_timestamp)
            kdes_timestamp[identifier] = kde_timestamp

        if len(subset_duration) >= min_kde:
            kde_duration, bandwidth_duration = fit_kde(subset_duration)
            kdes_duration[identifier] = kde_duration

    return kdes_timestamp, kdes_duration

def fit_kde(subset):
    """
    Fit a Kernel Density Estimator to a given subset of data.
    """
    if len(subset) > 1:
        kde = gaussian_kde(subset.values, bw_method='scott')
        bandwidth = kde.scotts_factor() * subset.std(ddof=1)
    else:
        bandwidth = 0.5

    kde = KernelDensity(bandwidth=bandwidth, kernel='gaussian')
    kde.fit(subset.values.reshape(-1, 1))  # Reshape to 2D array
    return kde, bandwidth

def generate_new_events_kde(kde_timestamp, kde_duration, n_samples, timestamp_scaler, duration_scaler):
    """
    Generate new events using the KDE models for timestamps and durations.
    Ensures that the desired number of valid samples is obtained.
    """
    valid_samples = 0
    all_timestamps = []
    all_durations = []

    while valid_samples < n_samples:
        remaining_samples = n_samples - valid_samples

        # Generate samples
        timestamps = kde_timestamp.sample(remaining_samples)
        durations = kde_duration.sample(remaining_samples)

        # Inverse transform to original scale
        timestamps = timestamp_scaler.inverse_transform(timestamps)
        durations = duration_scaler.inverse_transform(durations)

        # Filter out invalid samples
        #valid_mask = (timestamps >= 0) & (durations >= 0)
        valid_mask = (timestamps >= 0) & (durations >= 0) & (durations <= timestamps)
        valid_timestamps = timestamps[valid_mask].reshape(-1, 1)
        valid_durations = durations[valid_mask].reshape(-1, 1)

        # Aggregate valid samples
        all_timestamps.append(valid_timestamps)
        all_durations.append(valid_durations)
        valid_samples += len(valid_timestamps)

    # Concatenate all valid samples for DataFrame
    final_timestamps = np.concatenate(all_timestamps, axis=0)
    final_durations = np.concatenate(all_durations, axis=0)

    return np.hstack([final_timestamps, final_durations])

def generate_events(identifier, n_samples, data, kdes_timestamp, kdes_duration, timestamp_scaler, duration_scaler, min_kde):
    """
    Generate events for a given identifier.
    """
    subset = data[data['event_id'] == identifier]
    if len(subset) > min_kde:
        return generate_new_events_kde(kdes_timestamp[identifier], kdes_duration[identifier], n_samples, timestamp_scaler, duration_scaler)
    else:
        # Repeat the event with the same duration at different timestamps
        duration = subset['duration'].iloc[0]
        min_timestamp, max_timestamp = data['end_timestamp'].min(), data['end_timestamp'].max()
        timestamps = np.random.uniform(min_timestamp, max_timestamp, size=(n_samples, 1))
        durations = np.full((n_samples, 1), duration)
        return np.hstack([timestamps, durations])

def generate_new_trace(data, kdes_timestamp, kdes_duration, total_events_to_generate, timestamp_scaler, duration_scaler, min_kde=1):
    """
    Generate a new trace based on the original data and KDE models.
    """
    new_trace = []
    event_counts = data['event_id'].value_counts(normalize=True)

    for identifier, freq in event_counts.items():
        n_samples = int(freq * total_events_to_generate)
        new_events = generate_events(identifier, n_samples, data, kdes_timestamp, kdes_duration, timestamp_scaler, duration_scaler, min_kde)
        for event in new_events:
            new_trace.append({'event_id': identifier, 'end_timestamp': event[0], 'duration': event[1]})

    return pd.DataFrame(new_trace)

def prepare_for_export(new_trace_df):
    """
    Prepare the dataframe for export.
    """
    app_func_df = new_trace_df['event_id'].str.split('_', expand=True)
    app_func_df.columns = ['app', 'func']
    new_trace_df = pd.concat([app_func_df, new_trace_df[['end_timestamp', 'duration']]], axis=1)
    return new_trace_df

def print_descriptive_statistics(data, description):
    """
    Print descriptive statistics for the given dataset.
    """
    descriptive_stats = data.groupby('event_id')[['end_timestamp', 'duration']].describe()
    print(f"\nDescriptive Statistics for {description}:")
    print(descriptive_stats)

def resample(input_file, output_file, total_events_to_generate, min_kde):
    data = load_and_preprocess_data(input_file)
    print_descriptive_statistics(data, "Original Trace")
    scaled_data, timestamp_scaler, duration_scaler = scale_data(data)
    kdes_timestamp, kdes_duration = fit_kde_estimators(scaled_data, min_kde)
    new_trace_df = generate_new_trace(data, kdes_timestamp, kdes_duration, total_events_to_generate, timestamp_scaler, duration_scaler, min_kde)
    new_trace_df_sorted = new_trace_df.sort_values(by='end_timestamp')
    print_descriptive_statistics(new_trace_df_sorted, "Generated Trace")
    final_df = prepare_for_export(new_trace_df_sorted)
    final_df.to_csv(output_file, index=False)
    print(f"Trace exported to '{output_file}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Resample trace data.')
    parser.add_argument('--input', type=str, default='trace.csv', help='Input trace')
    parser.add_argument('--output', type=str, default='new_trace.csv', help='Output trace')
    parser.add_argument('-n', type=int, default=10000000, help='Total number of events to generate')
    parser.add_argument('--min_kde', type=int, default=1, help='Minimum number of events to use KDE')
    args = parser.parse_args()

    resample(args.input, args.output, args.n, args.min_kde)
