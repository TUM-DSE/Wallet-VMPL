from simulate import main_sim


def proc(output_file, header, nb_nodes, cold_boot, warm_boot, soft_warm_boot, cache_size, cache_duration, execution_slots, soft_warm_rate):
    f = open(output_file, "w")
    f.write(header)
    with f as sys.stdout:
        main_sim=(nb_nodes, cold_boot, warm_boot, soft_warm_boot, cache_szie, cache_duration, execution_slots, soft_warm_rate)

def main():
    #num_nodes = [16, 64, 256, 1024]
    #num_nodes = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
    num_nodes = [1, 2]
    cache_size = 1

    # return_vals [sim_time, cold_boots %, sot_warm_boots %, warm_boots %, avg func delay, median func delay, std func delay]


    # CVM simulation
    cvm_cold_boot_time = 8.3073
    cvm_warm_boot_time = 0.0677
    cvm_max_execution_slots = 1
    cvm_results = [0] * len(num_nodes)
   # print(cvm_results)
    for i in range(len(num_nodes)):
        print("************* CVM ****************")
        n = num_nodes[i]
        results = main_sim(n, cvm_cold_boot_time, cvm_warm_boot_time, 0, cache_size, 300, cvm_max_execution_slots, 0)
        cvm_results[i] = results[0]
        #print(results)

    #print(cvm_results)

    # VM simulation
    vm_cold_boot_time = 3.6999
    vm_warm_boot_time = 0.0663
    vm_max_execution_slots = 1
    vm_results = [0] * len(num_nodes)
    for i in range(len(num_nodes)):
        print("************* VM ****************")
        n = num_nodes[i]
        results = main_sim(n, vm_cold_boot_time, vm_warm_boot_time, 0, cache_size, 300, vm_max_execution_slots, 0)
        vm_results[i] = results[0]
        #print(results)


    # Wallet simulation
    w_percentage_soft_warm = [0]
    w_cold_boot_time = 4.3061
    w_warm_boot_time = 1.6766
    w_soft_warm_time = 2.4124
    w_max_execution_slots = 1
    w_results = [0] * len(num_nodes)
    for i in range(len(num_nodes)):
        for j in range(len(w_percentage_soft_warm)):
            print("************* WALLET ****************")
            n = num_nodes[i]
            percent_soft_warm = w_percentage_soft_warm[j]
            results = main_sim(n, w_cold_boot_time, w_warm_boot_time, w_soft_warm_time, cache_size, 300, w_max_execution_slots, percent_soft_warm)
            #print(results)
            # this ignores earlier soft warm percentage :)
            w_results[i] = results[0]

    #print(vm_results)
    #print(cvm_results)
    #print(w_results)
    #output = f'num_nodes;vm_results;cvm_results;w_results\n{num_nodes};{vm_results};{cvm_results};{w_results}\n'
    #print(output)

    #file = open("node_scalability.csv", "w")
    #file.write(output)
    #file.close()

if __name__ == '__main__':
    main()


