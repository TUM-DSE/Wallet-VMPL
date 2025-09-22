from simulate import main_sim
from multiprocessing import Pool, cpu_count
import sys
import os

def proc(output_file, header, nb_nodes, cold_boot, cold_std, warm_boot, warm_std, soft_warm_boot, soft_warm_std, cache_size, cache_duration, execution_slots, soft_warm_rate, pbar_position, input_file, enable_dynamic_sw):
    f = open(output_file, "w")
    f.write(header)
    with f as sys.stdout:
        main_sim(nb_nodes, cold_boot, cold_std, warm_boot, warm_std, soft_warm_boot, soft_warm_std, cache_size, cache_duration, execution_slots, soft_warm_rate, pbar_position, input_file, enable_dynamic_sw)
    #f.close()

def main():
    n_proc = cpu_count
    pool = Pool(processes=(cpu_count()))
    tmp_file_num = 0
    input_file = sys.argv[1]

    num_nodes = [50, 75, 100, 125, 150]
    cache_sizes = [32]
    execution_slots = [32]
    cache_time = 600

    cvm_cold_boot_time = 8.3073
    cvm_cold_std = 0.1825
    cvm_warm_boot_time = 0.0677
    cvm_warm_std =  0.003515
    #cvm_warm_boot_time = 0.003
    cvm_max_execution_slots = 64
    cvm_header = "************* CVM ****************\n"

    vm_cold_boot_time = 3.6999
    vm_cold_std = 0.03749
    vm_warm_boot_time = 0.0663
    vm_warm_std = 0.003447
    #vm_warm_boot_time = 0.003
    vm_max_execution_slots = 64
    vm_header = "************* VM ****************\n"

    w_percentage_soft_warm = [0]
    w_cold_boot_time = 1.56118
    w_cold_std = 0.01826776
    w_warm_boot_time = 0.005
    w_warm_std = 0.00003
    w_soft_warm_time = 0.0057
    w_soft_warm_std = 0.000056
    w_max_execution_slots = 64
    enable_dynamic_sw = True
    w_header = "************* WALLET ****************\n"

    k_cold_boot_time = 1.394
    k_cold_std = 0.100466
    k_warm_boot_time = 0.0021
    k_warm_std = 0.0001
    k_max_execution_slots = 64
    k_header = "************* KATA ****************\n"

    print(f'Starting {len(num_nodes) * len(cache_sizes) * len(execution_slots) * (len(w_percentage_soft_warm) + 2) } simulations')
    for n in num_nodes:
        for exec_slot in execution_slots:
            for cache_size in cache_sizes:
                cvm_max_execution_slots = exec_slot
                vm_max_execution_slots =  exec_slot
                w_max_execution_slots = exec_slot
                k_max_execution_slots = exec_slot

                # CVM simulation
                pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', cvm_header, n, cvm_cold_boot_time, cvm_cold_std, cvm_warm_boot_time, cvm_warm_std, 0, 0, cache_size, cache_time, cvm_max_execution_slots, 0, tmp_file_num, input_file, False))
                tmp_file_num += 1

                # VM simulation
                pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', vm_header, n, vm_cold_boot_time, vm_cold_std, vm_warm_boot_time, vm_warm_std, 0, 0, cache_size, cache_time, vm_max_execution_slots, 0, tmp_file_num, input_file, False))
                tmp_file_num += 1

                # Wallet simulation
                for percent_soft_warm in w_percentage_soft_warm:
                    pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', w_header, n, w_cold_boot_time, w_cold_std,  w_warm_boot_time, w_warm_std, w_soft_warm_time,  w_soft_warm_std, cache_size, cache_time, w_max_execution_slots, percent_soft_warm, tmp_file_num, input_file, enable_dynamic_sw))
                    tmp_file_num += 1

                # Kata simulation
                pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', k_header, n, k_cold_boot_time, k_cold_std, k_warm_boot_time, k_warm_std, 0, 0, cache_size, cache_time, k_max_execution_slots, 0, tmp_file_num, input_file, False))
                tmp_file_num += 1

    pool.close()
    pool.join()

    # concatenate all temporary files into a single one
    f = open("simulation_results_parallel.txt", "w")
    for i in range(tmp_file_num):
        infile_path = f'tmp_file_{i}.txt';
        with open(infile_path, 'r') as infile:
            f.write(infile.read())
        os.remove(infile_path)

    # delete temporary files


if __name__ == '__main__':
    main()


