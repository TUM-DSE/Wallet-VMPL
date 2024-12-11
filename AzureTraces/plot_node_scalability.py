from simulate import main_sim

def main():
    #num_nodes = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
    num_nodes = [1, 2]


    # return_vals [sim_time, cold_boots %, sot_warm_boots %, warm_boots %, avg func delay, median func delay, std func delay]

    
    cache_size = 8

    # CVM simulation
    cvm_cold_boot_time = 10
    cvm_warm_boot_time = 1
    cvm_max_execution_slots = 4
    cvm_results = [0] * len(num_nodes)
    print(cvm_results)
    for i in range(len(num_nodes)):
        n = num_nodes[i]
        results = main_sim(n, cvm_cold_boot_time, cvm_warm_boot_time, 0, cache_size, 300, cvm_max_execution_slots, 0)
        cvm_results[i] = results[0]
    print(cvm_results)

    # VM simulation
    vm_cold_boot_time = 2
    vm_warm_boot_time = 1
    vm_max_execution_slots = 4
    vm_results = [0] * len(num_nodes)
    for i in range(len(num_nodes)):
        n = num_nodes[i]
        results = main_sim(n, vm_cold_boot_time, vm_warm_boot_time, 0, cache_size, 300, vm_max_execution_slots, 0)
        vm_results[i] = results[0]


    # Wallet simulation
    w_cold_boot_time = 1
    w_warm_boot_time = 0.3
    w_max_execution_slots = 4
    w_results = [0] * len(num_nodes)
    for i in range(len(num_nodes)):
        n = num_nodes[i]
        results = main_sim(n, w_cold_boot_time, w_warm_boot_time, 0, cache_size, 300, w_max_execution_slots, 0.3)
        w_results[i] = results[0]

    print(vm_results)
    print(cvm_results)
    print(w_results)

if __name__ == '__main__':
    main()


