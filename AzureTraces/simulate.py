import csv
import numpy as np
from tqdm import tqdm
import time

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
def log(msg):
    global file
    global log_active
    global cur_logs
    if not log_active or (cur_logs >= max_logs):
        return
    file.write(msg + '\n')
    cur_logs = cur_logs + 1




def update_cached_functions(nodes, simulation_increment, caching_time):
    for node in nodes:
        for i in range(node.max_functions):
            if node.function_slots_free[i] == False:
                node.function_last_call_time[i] = node.function_last_call_time[i] + simulation_increment
                if node.function_last_call_time[i] > caching_time:
                    log(f'Evicting stale function {node.functions_registered[i]} from cache slot {i} on node {node.node_id}')
                    node.function_slots_free[i] = True
    

def update_simulation(nodes, next_function_time, simulation_time, caching_time, 
                      run_until_node_free):

    # increase time until either a function finished executing 
    # or until the next function arrives
    old_simulation_time = simulation_time

    next_func_finish = None
    next_func_finish_val = 0;
    node_of_next_func = None
    for node in nodes:
        if node.curr_function != None:
            if next_func_finish == None:
                next_func_finish = node.curr_function
                next_func_finish_val = node.curr_function.end_time
                node_of_next_func = node
            else:
                if(node.curr_function.end_time < next_func_finish_val):
                    next_func_finish = node.curr_function
                    next_func_finish_val = node.curr_function.end_time
                    node_of_next_func = node

    if run_until_node_free:
        # don't look at when to start next function since we don't have free nodes
        # rather, run unil a free node appears
        if(next_func_finish_val < simulation_time):
            print("Error: going back in time!")
            printf()
            exit(-1)
        simulation_time = next_func_finish_val
        new_func = False
        simulation_increment = simulation_time - old_simulation_time
        log(f'[{simulation_time}] Function {node_of_next_func.curr_function.func_hash} has finished executing on node {node_of_next_func.node_id}')
        node_of_next_func.curr_function = None
        update_cached_functions(nodes, simulation_increment, caching_time)
        return simulation_increment, simulation_time, new_func


    # check if we have a function that finished first or if we have a 
    # function that arrives first


    if node_of_next_func != None and next_func_finish_val <= next_function_time:
        # mark the function as finished
        if(next_func_finish_val < simulation_time):
            print("Error: going back in time!")
            printf()
            exit(-1)
        simulation_time = next_func_finish_val
        new_func = False
        simulation_increment = simulation_time - old_simulation_time
        log(f'[{simulation_time}] Function {node_of_next_func.curr_function.func_hash} has finished executing on node {node_of_next_func.node_id}')
        node_of_next_func.curr_function = None
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
        log(f'[{simulation_time}] New function at {next_function_time} can start executing')
        return simulation_increment, simulation_time, new_func

def cache_function(node, f):
    f_id = f.application_hash + f.func_hash
    # try to find a free spot in the cache
    for i in range(node.max_functions):
        if node.function_slots_free[i] == True:
            node.function_slots_free[i] = False
            node.functions_registered[i] = f_id 
            node.function_last_call_time[i] = 0
            return i            

    # if no free slot available, replace the least recently used

    max_time = 0
    max_slot = 0
    for i in range(node.max_functions):
        if node.function_last_call_time[i] > max_time:
            max_time = node.function_last_call_time[i]
            max_slot = i
    log(f'Function {f_id} is replacing function {node.functions_registered[max_slot]} in slot {max_slot} on node {node.node_id}')
    node.functions_registered[max_slot] = f_id
    node.function_last_call_time[max_slot] = 0
    return max_slot

def main():
    # default parameter values
    num_nodes = 5
    cold_boot_time = 0.3
    warm_boot_time = 0.1
    max_functions_per_node = 3
    caching_time = 5 * 60
    max_execution_slots = 5


    # index into the csv
    app_hash = 0
    func_hash = 1
    duration = 3
    arrival_time = 4


    #statistics
    sim_time = 0
    total_delay = 0
    cold_boots = 0

    # read csv
    input_file = 'AzureFunctionsInvocationTraceForTwoWeeksJan2021_preprocessed.csv'
    with open(input_file, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        header = np.array(next(reader), dtype=object)  # Read the header row
        rows = [np.array(row, dtype=object) for row in reader]

    # create array of nodes
    nodes = [Node() for i in range(num_nodes)];
    for i in range(len(nodes)):
        nodes[i].max_functions = max_functions_per_node
        nodes[i].function_slots_free = [True for j in range(nodes[i].max_functions)]
        nodes[i].node_id = i;
        nodes[i].functions_registered = ['' for j in range(nodes[i].max_functions)]
        nodes[i].function_last_call_time = [0 for j in range(nodes[i].max_functions)]
        nodes[i].max_execution_slots = max_execution_slots
        nodes[i].execution_slots = [None for j in range(nodes[i].max_execution_slots)]
        #print(nodes[i].function_slots_free)
        #print(nodes[i].functions_registered)


    scheduler = SimpleScheduler()
    pbar = tqdm(total=len(rows))
    cur_func = 0
    while cur_func < len(rows):
        
        row = rows[cur_func]

        # create function
        f = Function()
        f.arrival_time = float(row[arrival_time])
        f.duration = float(row[duration])
        f.application_hash = row[app_hash]
        f.func_hash = row[func_hash]

        # get possible node for next function
        f_delay = 0;
        assigned_node, _, _ = scheduler.pick_next_node(nodes, f)
        # if there are no free node, run until a new node can be selected
        f_sched_time = max(sim_time, f.arrival_time)
        while(assigned_node == None):
            log(f'[{sim_time}] No free nodes available')
            _, sim_time, _ = update_simulation(nodes, f_sched_time, sim_time, caching_time, True)
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
        if cold_boot == True:
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
        log(f'Function {f.application_hash + f.func_hash} has been cached in slot {cache_slot} on node {assigned_node.node_id}')

        f_delay = f.start_time - f.arrival_time
        total_delay = total_delay + f_delay
        if cold_boot == True:
            cold_boots = cold_boots + 1
        log(f'[{sim_time}] Function {f.func_hash} starts executing on node {assigned_node.node_id} after a delay of {f_delay}. Execution duration: {f.duration}, Cold boot: {cold_boot}')

        cur_func = cur_func + 1
        pbar.update(1)

    pbar.close()
    print(f'Statistics:')
    print(f'Total simulation time: {sim_time}')
    print(f'Cold boot rate: {cold_boots / len(rows)}')
    print(f'Avg function delay: {total_delay / len(rows)}')

        

if __name__ == '__main__':
    main()



