import csv
import numpy as np
from tqdm import tqdm
import time
import random
import argparse
import sys

# my scripts
from scheduler import SimpleScheduler

class Function:
    arrival_time: float
    start_time: float
    duration: float
    end_time: float
    application_hash: str
    func_hash: str

class Node:
    node_id: int
    max_functions: int
    functions_registered: []
    function_slots_free: []
    function_last_call_time: []
    max_execution_slots: []
    execution_slots: []

file = open("simulation_log.txt", "w")
log_active = False
max_logs = 10000
cur_logs = 0

# Globals for simulation
max_cache_util  = 0
cur_cache_util = 0

def log(msg):
    #print(msg)
    #time.sleep(1)

    global file
    global log_active
    global cur_logs
    if not log_active or (cur_logs >= max_logs):
        return
    file.write(msg + '\n')
    cur_logs = cur_logs + 1




def update_cached_functions(nodes, simulation_increment, caching_time):
    global cur_cache_util
    for node in nodes:
        for i in range(node.max_functions):
            if node.function_slots_free[i] == False:
                node.function_last_call_time[i] = node.function_last_call_time[i] + simulation_increment
                if node.function_last_call_time[i] > caching_time:
                    #log(f'Evicting stale function {node.functions_registered[i]} from cache slot {i} on node {node.node_id}')
                    node.function_slots_free[i] = True
                    cur_cache_util = cur_cache_util - 1


def get_earliest_func_finish(nodes):
    func_earliest = None
    node_earliest = None
    slot_earliest = 0

    for node in nodes:
        for i in range(node.max_execution_slots):
            if node.execution_slots[i] != None:
                if func_earliest == None:
                    func_earliest = node.execution_slots[i]
                    node_earliest = node
                    slot_earliest = i
                else:
                    if node.execution_slots[i].end_time < func_earliest.end_time:
                        func_earliest = node.execution_slots[i]

                        node_earliest = node
                        slot_earliest = i

    return node_earliest, slot_earliest, func_earliest




def update_simulation(nodes, next_function_time, simulation_time, caching_time,
                      run_until_node_free):

    # increase time until either a function finished executing
    # or until the next function arrives
    old_simulation_time = simulation_time

    node_earliest, slot_earliest, func_earliest = get_earliest_func_finish(nodes)

    if run_until_node_free:
        # don't look at when to start next function since we don't have free nodes
        # rather, run unil a free node appears
        if(func_earliest.end_time < simulation_time):
            print("Error: going back in time!")
            printf()
            exit(-1)
        simulation_time = func_earliest.end_time
        new_func = False
        simulation_increment = simulation_time - old_simulation_time
        #log(f'[{simulation_time}] Function {node_earliest.execution_slots[slot_earliest].func_hash} has finished executing on node {node_earliest.node_id} slot {slot_earliest}')
        node_earliest.execution_slots[slot_earliest] = None
        update_cached_functions(nodes, simulation_increment, caching_time)
        return simulation_increment, simulation_time, new_func


    # check if we have a function that finished first or if we have a
    # function that arrives first


    if node_earliest != None and func_earliest.end_time <= next_function_time:
        # mark the function as finished
        if(func_earliest.end_time < simulation_time):
            print("Error: going back in time!")
            printf()
            exit(-1)
        simulation_time = func_earliest.end_time
        new_func = False
        simulation_increment = simulation_time - old_simulation_time
        #log(f'[{simulation_time}] Function {node_earliest.execution_slots[slot_earliest].func_hash} has finished executing on node {node_earliest.node_id} slot {slot_earliest}')
        node_earliest.execution_slots[slot_earliest] = None
        update_cached_functions(nodes, simulation_increment, caching_time)
        return simulation_increment, simulation_time, new_func
    else:
        if(next_function_time < simulation_time):
            print("Error: going back in time!")
            printf()
            exit(-1)
        simulation_time = next_function_time
        new_func = True;
        simulation_increment = simulation_time - old_simulation_time
        update_cached_functions(nodes,simulation_increment, caching_time)
        #log(f'[{simulation_time}] New function at {next_function_time} can start executing')
        return simulation_increment, simulation_time, new_func

def cache_function(node, f):
    global cur_cache_util
    global max_cache_util
    f_id = f.application_hash + f.func_hash

    # check if function is already cached
    for i in range(node.max_functions):
        if node.function_slots_free[i] == False and node.functions_registered[i] == f_id:
            # reset last used
            node.function_last_call_time[i] = 0
            return i

    # try to find a free spot in the cache
    for i in range(node.max_functions):
        if node.function_slots_free[i] == True:
            node.function_slots_free[i] = False
            node.functions_registered[i] = f_id
            node.function_last_call_time[i] = 0
            cur_cache_util = cur_cache_util + 1
            if cur_cache_util > max_cache_util:
                max_cache_util = cur_cache_util
            return i

    # if no free slot available, replace the least recently used

    max_time = 0
    max_slot = 0
    for i in range(node.max_functions):
        if node.function_last_call_time[i] > max_time:
            max_time = node.function_last_call_time[i]
            max_slot = i
    #log(f'Function {f_id} is replacing cached function {node.functions_registered[max_slot]} in slot {max_slot} on node {node.node_id}')
    node.functions_registered[max_slot] = f_id
    node.function_last_call_time[max_slot] = 0
    return max_slot

def is_any_active(nodes):
    for node in nodes:
        for f in node.execution_slots:
            if f != None:
                return True
    return False

def main_sim(num_nodes, cold_boot_time, warm_boot_time, soft_warm_time, max_functions_per_node, caching_time, max_execution_slots, percentage_soft_warm, pbar_position, input_file):

    # index into the csv
    app_hash = 0
    func_hash = 1
    duration = 3
    arrival_time = 4


    #statistics
    sim_time = 0
    total_delay = 0
    cold_boots = 0
    soft_warm_boots = 0
    warm_boots = 0
    total_cache_slots = 0

    #initialize rng
    random.seed()

    # read csv
    # input_file = 'AzureFunctionsInvocationTraceForTwoWeeksJan2021_preprocessed.csv'
    # input_file = 'resampled_preprocessed.csv'
    with open(input_file, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        header = np.array(next(reader), dtype=object)  # Read the header row
        rows = [np.array(row, dtype=object) for row in reader]

    # create array of nodes
    nodes = [Node() for i in range(num_nodes)];
    for i in range(len(nodes)):
        # max functions cached per node
        nodes[i].max_functions = max_functions_per_node
        total_cache_slots = total_cache_slots + nodes[i].max_functions

        nodes[i].function_slots_free = [True for j in range(nodes[i].max_functions)]
        nodes[i].node_id = i;
        nodes[i].functions_registered = ['' for j in range(nodes[i].max_functions)]
        nodes[i].function_last_call_time = [0 for j in range(nodes[i].max_functions)]
        nodes[i].max_execution_slots = max_execution_slots
        nodes[i].execution_slots = [None for j in range(nodes[i].max_execution_slots)]
        #print(nodes[i].function_slots_free)
        #print(nodes[i].functions_registered)


    scheduler = SimpleScheduler()
    delays = np.empty(len(rows))
    per_func_delays = dict()
    pbar = tqdm(total=len(rows), position=0)
    cur_func = 0
    while cur_func < len(rows):

        row = rows[cur_func]

        # create function
        f = Function()
        f.arrival_time = float(row[arrival_time])
        f.duration = float(row[duration])
        f.application_hash = row[app_hash]
        f.func_hash = row[func_hash]
        curr_f_id = f.application_hash + "-" + f.func_hash
        if not (curr_f_id in per_func_delays):
            per_func_delays[curr_f_id] = []

        # get possible node for next function
        f_delay = 0;
        assigned_node, _, _ = scheduler.pick_next_node(nodes, f)
        # if there are no free node, run until a new node can be selected
        f_sched_time = max(sim_time, f.arrival_time)
        while(assigned_node == None):
            #log(f'[{sim_time}] No free nodes available')
            _, sim_time, _  = update_simulation(nodes, f_sched_time, sim_time, caching_time, True)
            assigned_node, _ , _ = scheduler.pick_next_node(nodes, f)

        # we now have a canditate node, simulate until this function can run
        # take into account any delays
        f_sched_time = max(sim_time, f.arrival_time)
        _, sim_time, func_scheduled = update_simulation(nodes, f_sched_time, sim_time, caching_time, False)
        while func_scheduled == False:
            f_sched_time = max(sim_time, f.arrival_time)
            _, sim_time, func_scheduled = update_simulation(nodes, f_sched_time, sim_time, caching_time,  False)

        # finally time to schedule function
        f.start_time = sim_time

        #look for nodes again, just in case there is a better one than the previous candidate
        assigned_node, assigned_slot, cold_boot = scheduler.pick_next_node(nodes, f)
        soft_warm = False
        if cold_boot == True:
            if random.random() < percentage_soft_warm:
                f.duration = f.duration + soft_warm_time
                soft_warm = True
            else:
                f.duration = f.duration + cold_boot_time
        else:
            f.duration = f.duration + warm_boot_time

        f.end_time = f.start_time + f.duration

        if assigned_node == None:
            # this should never happen
            print("ERROR: No free node found even though there should be a candidate!")
            exit(-1);

        # assign function to node
        assigned_node.execution_slots[assigned_slot] = f
        cache_slot = cache_function(assigned_node, f)
        #log(f'Function {f.application_hash + f.func_hash} has been cached in slot {cache_slot} on node {assigned_node.node_id}')

        f_delay = f.start_time - f.arrival_time
        total_delay = total_delay + f_delay
        delays[cur_func] = f_delay
        per_func_delays[curr_f_id].append(f_delay)

        if soft_warm == True:
            soft_warm_boots = soft_warm_boots + 1
        elif cold_boot == True:
            cold_boots = cold_boots + 1
        else:
            warm_boots = warm_boots + 1

        #log(f'[{sim_time}] Function {f.func_hash} starts executing on node {assigned_node.node_id} slot {assigned_slot} after a delay of {f_delay}. Execution duration: {f.duration}, Cold boot: {cold_boot}, Soft warm boot: {soft_warm}')

        cur_func = cur_func + 1
        pbar.update(1)

    # TODO: Finish executing currently running functions
    while is_any_active(nodes):
        _, sim_time, _ = update_simulation(nodes, 0, sim_time, caching_time, True)


    pbar.close()
    #output = '------------------------------------------------\nStatistics:\n'
    #output = output + f'Total simulation time: {sim_time}\n'
    #output = output + f'Cold boot rate: {cold_boots / len(rows)}\n'
    #output = output + '------------------------------------------------\n'
    #return output
    print('------------------------------------------------')
    print(f'Statistics:')
    print(f'Delays:')
    func_ids = list(per_func_delays.keys())
    for id in func_ids:
        print(f"     {id} : {per_func_delays[id]}")

    print(f'Total simulation time: {sim_time}')
    print(f'Cold boot rate: {cold_boots / len(rows)} ({cold_boots})')
    print(f'Soft warm boot rate: {soft_warm_boots / len(rows)} ({soft_warm_boots})')
    print(f'Warm boot rate: {warm_boots / len(rows)} ({warm_boots})')
    print(f'Function delay:')
    print(f'    Avg: {np.average(delays)}')
    print(f'    Median: {np.median(delays)}')
    print(f'    Std: {np.std(delays)}')
    print(f'Max cache utilization: {max_cache_util/total_cache_slots}, ({max_cache_util}/{total_cache_slots})')

    print(f'')
    print(f'Configuration:')
    print(f'num_nodes: {num_nodes}')
    print(f'cold_boot_time: {cold_boot_time}')
    print(f'warm_boot_time: {warm_boot_time}')
    print(f'soft_warm_time: {soft_warm_time}')
    print(f'max_functions_cached_per_node: {max_functions_per_node}')
    print(f'caching_time: {caching_time}')
    print(f'max_executions_slots: {max_execution_slots}')
    print(f'percentage_soft_warm: {percentage_soft_warm}')
    print('------------------------------------------------')

    return [sim_time, cold_boots/len(rows), soft_warm_boots / len(rows), warm_boots / len(rows), np.average(delays), np.median(delays), np.std(delays)]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simulate the azure traces.')
    parser.add_argument('-num_nodes', type=int, default=5, help='Number of nodes in the simulation.')
    parser.add_argument('-cold_penalty', type=float, help='Penalty incurred by a function during a cold start (in seconds).', required=True)
    parser.add_argument('-warm_penalty', type=float, help='Penalty incurred by a function during a warm start (in seconds).', required=True)
    parser.add_argument('-soft_warm_penalty', type=float, default=0, help='Penalty incurred by a function during a soft warm start (in seconds). In the normal case, this would be equal to the cold boot penalty. In Wallet\'s case, this is the latency of starting a function that isn\'t cached, but whose zygote is already loaded.')
    parser.add_argument('-cache_size', type=int, default=10, help='Number of functions that can be cached on a node concurrently.')
    parser.add_argument('-caching_time', type=float, default= 300, help='The time (in seconds) after which an unused cached function will be automatically evicted.')
    parser.add_argument('-execution_slots', type=int, default=3, help='The number of functions that can be executed concurrently on a node.')
    parser.add_argument('-percentage_soft_warm', type=float, default=0, help='The percentage of cold boots that get turned into soft warm boots.')
    parser.add_argument('-input_file', type=str, default='', required=True, help='The input file that contains the trace')
    args = parser.parse_args()

    # default parameter values
    num_nodes = args.num_nodes
    cold_boot_time = args.cold_penalty
    warm_boot_time = args.warm_penalty
    soft_warm_time = args.soft_warm_penalty
    max_functions_per_node = args.cache_size
    caching_time = args.caching_time
    max_execution_slots = args.execution_slots
    percentage_soft_warm = args.percentage_soft_warm
    input_file = args.input_file
    out = main_sim(num_nodes, cold_boot_time, warm_boot_time, soft_warm_time, max_functions_per_node, caching_time, max_execution_slots, percentage_soft_warm, 1, input_file)
    print(out)



