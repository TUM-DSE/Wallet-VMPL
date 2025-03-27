from simulate import main_sim
from multiprocessing import Pool, cpu_count
import sys
import os

def proc(output_file, header, nb_nodes, cold_boot, warm_boot, soft_warm_boot, cache_size, cache_duration, execution_slots, soft_warm_rate, pbar_position, input_file):
    f = open(output_file, "w")
    f.write(header)
    with f as sys.stdout:
        main_sim(nb_nodes, cold_boot, warm_boot, soft_warm_boot, cache_size, cache_duration, execution_slots, soft_warm_rate, pbar_position, input_file)
    #f.close()

def main():
    n_proc = cpu_count
    pool = Pool(processes=(cpu_count()))
    tmp_file_num = 0
    input_file = sys.argv[1]

    num_nodes = [70, 80, 90, 100, 110, 120, 130, 140]
    cache_sizes = [64]
    execution_slots = [4]
    cache_time = 600

    cvm_cold_boot_time = 8.3073
    cvm_warm_boot_time = 0.0677
    #cvm_warm_boot_time = 0.003
    cvm_max_execution_slots = 64
    cvm_header = "************* CVM ****************\n"

    vm_cold_boot_time = 3.6999
    vm_warm_boot_time = 0.0663
    #vm_warm_boot_time = 0.003
    vm_max_execution_slots = 64
    vm_header = "************* VM ****************\n"

    w_percentage_soft_warm = [0, 0.5]
    w_cold_boot_time = 1.56118
    w_warm_boot_time = 0.005
    w_soft_warm_time = 0.0057
    w_max_execution_slots = 64
    w_header = "************* WALLET ****************\n"

    k_cold_boot_time = 1.394
    k_warm_boot_time = 0
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
                pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', cvm_header, n, cvm_cold_boot_time, cvm_warm_boot_time, 0, cache_size, cache_time, cvm_max_execution_slots, 0, tmp_file_num, input_file))
                tmp_file_num += 1

                # VM simulation
                pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', vm_header, n, vm_cold_boot_time, vm_warm_boot_time, 0, cache_size, cache_time, vm_max_execution_slots, 0, tmp_file_num, input_file))
                tmp_file_num += 1

                # Wallet simulation
                for percent_soft_warm in w_percentage_soft_warm:
                    pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', w_header, n, w_cold_boot_time, w_warm_boot_time, w_soft_warm_time, cache_size, cache_time, w_max_execution_slots, percent_soft_warm, tmp_file_num, input_file))
                    tmp_file_num += 1

                # Kata simulation
                pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', k_header, n, k_cold_boot_time, k_warm_boot_time, 0, cache_size, cache_time, k_max_execution_slots, 0, tmp_file_num, input_file))
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


