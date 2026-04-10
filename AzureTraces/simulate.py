import csv
import numpy as np
from tqdm import tqdm
import heapq
import argparse
import sys
from dataclasses import dataclass, field


@dataclass
class Chain:
    app_hash: str
    active_requests: int = 0
    last_active_time: float = 0.0


def main_sim(total_cores, cold_start_time, cold_start_std,
             reschedule_time, reschedule_std,
             concurrent_per_vnf, cores_per_chain, max_vms,
             pbar_position, input_file):

    # Derived limits
    max_chains = total_cores // cores_per_chain
    if max_vms > 0:
        max_chains = min(max_chains, max_vms // cores_per_chain)

    # Cluster state: app_hash -> list of Chain objects
    app_chains: dict[str, list[Chain]] = {}
    all_chains: list[Chain] = []
    used_cores = 0

    # Event heap: (end_time, chain_index_in_all_chains)
    event_heap: list[tuple[float, int]] = []

    # Statistics
    cold_starts = 0
    reschedules = 0
    total_requests = 0

    # Read CSV
    with open(input_file, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader)  # skip header
        rows = []
        for row in reader:
            # app, func, end_timestamp, duration, memory
            end_ts = float(row[2])
            duration = float(row[3])
            arrival = end_ts - duration
            rows.append((arrival, duration, row[0]))  # (arrival_time, duration, app_hash)

    # Sort by arrival time
    rows.sort(key=lambda r: r[0])
    total_requests = len(rows)

    delays = np.empty(total_requests)
    sim_time = 0.0
    max_concurrent_chains = 0

    pbar = tqdm(total=total_requests, position=pbar_position, leave=True)

    def drain_completed(up_to_time):
        """Pop all events that complete by up_to_time, update chain state."""
        while event_heap and event_heap[0][0] <= up_to_time:
            end_t, chain_idx = heapq.heappop(event_heap)
            chain = all_chains[chain_idx]
            chain.active_requests -= 1
            chain.last_active_time = end_t

    def find_lru_idle_chain():
        """Find the idle chain (active_requests == 0) with earliest last_active_time."""
        best = None
        best_time = float('inf')
        for i, chain in enumerate(all_chains):
            if chain.active_requests == 0 and chain.last_active_time < best_time:
                best = i
                best_time = chain.last_active_time
        return best

    for req_idx in range(total_requests):
        arrival_time, duration, app_hash = rows[req_idx]

        # Advance sim_time to at least arrival
        sim_time = max(sim_time, arrival_time)
        drain_completed(sim_time)

        # Try to find an existing chain for this app with capacity
        assigned_chain = None
        assigned_cold = False

        if app_hash in app_chains:
            for chain in app_chains[app_hash]:
                if chain.active_requests < concurrent_per_vnf:
                    assigned_chain = chain
                    break

        if assigned_chain is not None:
            # Re-scheduling: existing chain has capacity
            boot_time = max(0.0, np.random.normal(reschedule_time, reschedule_std))
            reschedules += 1
        else:
            # Need a new chain - either free cores or evict
            if used_cores + cores_per_chain <= total_cores and \
               (max_vms <= 0 or len(all_chains) < max_vms // cores_per_chain):
                # Free cores available - create new chain
                new_chain = Chain(app_hash=app_hash)
                all_chains.append(new_chain)
                if app_hash not in app_chains:
                    app_chains[app_hash] = []
                app_chains[app_hash].append(new_chain)
                used_cores += cores_per_chain
                assigned_chain = new_chain
                assigned_cold = True
            else:
                # Try to evict an idle chain (LRU)
                idle_idx = find_lru_idle_chain()
                if idle_idx is not None:
                    # Evict
                    old_chain = all_chains[idle_idx]
                    old_app = old_chain.app_hash
                    app_chains[old_app].remove(old_chain)
                    if not app_chains[old_app]:
                        del app_chains[old_app]

                    # Replace with new chain
                    new_chain = Chain(app_hash=app_hash)
                    all_chains[idle_idx] = new_chain
                    if app_hash not in app_chains:
                        app_chains[app_hash] = []
                    app_chains[app_hash].append(new_chain)
                    assigned_chain = new_chain
                    assigned_cold = True
                else:
                    # No idle chains - wait for earliest event to complete
                    while assigned_chain is None:
                        if not event_heap:
                            # Should not happen if model is consistent
                            print("ERROR: No events in heap but no idle chains", file=sys.stderr)
                            break

                        # Advance to next event
                        next_end = event_heap[0][0]
                        sim_time = max(sim_time, next_end)
                        drain_completed(sim_time)

                        # Retry: check existing chain with capacity
                        if app_hash in app_chains:
                            for chain in app_chains[app_hash]:
                                if chain.active_requests < concurrent_per_vnf:
                                    assigned_chain = chain
                                    break

                        if assigned_chain is not None:
                            # Found capacity via re-scheduling
                            break

                        # Try eviction again
                        idle_idx = find_lru_idle_chain()
                        if idle_idx is not None:
                            old_chain = all_chains[idle_idx]
                            old_app = old_chain.app_hash
                            app_chains[old_app].remove(old_chain)
                            if not app_chains[old_app]:
                                del app_chains[old_app]

                            new_chain = Chain(app_hash=app_hash)
                            all_chains[idle_idx] = new_chain
                            if app_hash not in app_chains:
                                app_chains[app_hash] = []
                            app_chains[app_hash].append(new_chain)
                            assigned_chain = new_chain
                            assigned_cold = True

                    if assigned_chain is not None and not assigned_cold:
                        # Re-scheduling from wait loop
                        boot_time = max(0.0, np.random.normal(reschedule_time, reschedule_std))
                        reschedules += 1

            if assigned_cold:
                boot_time = max(0.0, np.random.normal(cold_start_time, cold_start_std))
                cold_starts += 1

        if assigned_chain is None:
            print("ERROR: Could not assign chain for request", file=sys.stderr)
            continue

        # Schedule the request
        start_time = sim_time
        end_time = start_time + boot_time + duration
        assigned_chain.active_requests += 1

        chain_idx = all_chains.index(assigned_chain)
        heapq.heappush(event_heap, (end_time, chain_idx))

        # Track max concurrent chains
        active_count = sum(1 for c in all_chains if c.active_requests > 0)
        if active_count > max_concurrent_chains:
            max_concurrent_chains = active_count

        # Record delay: (time request actually starts - arrival) + boot time
        delay = (start_time - arrival_time) + boot_time
        delays[req_idx] = delay

        pbar.update(1)

    # Drain remaining events
    while event_heap:
        end_t, chain_idx = heapq.heappop(event_heap)
        chain = all_chains[chain_idx]
        chain.active_requests -= 1
        chain.last_active_time = end_t
        sim_time = max(sim_time, end_t)

    pbar.close()

    cold_start_rate = cold_starts / total_requests if total_requests > 0 else 0
    reschedule_rate = reschedules / total_requests if total_requests > 0 else 0

    print('------------------------------------------------')
    print(f'Statistics:')
    print(f'Total requests: {total_requests}')
    print(f'Total simulation time: {sim_time}')
    print(f'Cold start rate: {cold_start_rate} ({cold_starts})')
    print(f'Reschedule rate: {reschedule_rate} ({reschedules})')
    print(f'Request delay:')
    print(f'    Avg: {np.average(delays)}')
    print(f'    Median: {np.median(delays)}')
    print(f'    Std: {np.std(delays)}')
    print(f'Max concurrent chains: {max_concurrent_chains}')
    print(f'')
    print(f'Configuration:')
    print(f'total_cores: {total_cores}')
    print(f'cold_start_time: {cold_start_time}')
    print(f'cold_start_std: {cold_start_std}')
    print(f'reschedule_time: {reschedule_time}')
    print(f'reschedule_std: {reschedule_std}')
    print(f'concurrent_per_vnf: {concurrent_per_vnf}')
    print(f'cores_per_chain: {cores_per_chain}')
    print(f'max_vms: {max_vms}')
    print('------------------------------------------------')

    return [sim_time, cold_start_rate, reschedule_rate,
            np.average(delays), np.median(delays), np.std(delays),
            max_concurrent_chains]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VNF chain simulation on Azure traces.')
    parser.add_argument('-total_cores', type=int, default=64, help='Total CPU cores available.')
    parser.add_argument('-cold_start', type=float, required=True, help='Eviction + cold start time (seconds).')
    parser.add_argument('-cold_start_std', type=float, default=0.0, help='Std dev for cold start time.')
    parser.add_argument('-reschedule', type=float, required=True, help='Re-scheduling time (seconds).')
    parser.add_argument('-reschedule_std', type=float, default=0.0, help='Std dev for re-scheduling time.')
    parser.add_argument('-concurrent_per_vnf', type=int, default=32, help='Max concurrent requests per VNF in a chain.')
    parser.add_argument('-cores_per_chain', type=int, default=3, help='CPU cores per VNF chain.')
    parser.add_argument('-max_vms', type=int, default=0, help='Max concurrent VMs (0 = unlimited).')
    parser.add_argument('-input_file', type=str, required=True, help='Input trace CSV file.')
    args = parser.parse_args()

    main_sim(args.total_cores, args.cold_start, args.cold_start_std,
             args.reschedule, args.reschedule_std,
             args.concurrent_per_vnf, args.cores_per_chain, args.max_vms,
             0, args.input_file)
