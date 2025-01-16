from simulate import main_sim
from multiprocessing import Pool, cpu_count
import sys
import os

def proc(output_file, header, nb_nodes, cold_boot, warm_boot, soft_warm_boot, cache_size, cache_duration, execution_slots, soft_warm_rate):
    f = open(output_file, "w")
    f.write(header)
    with f as sys.stdout:
        main_sim(nb_nodes, cold_boot, warm_boot, soft_warm_boot, cache_size, cache_duration, execution_slots, soft_warm_rate)
    #f.close()

def main():
    n_proc = cpu_count
    pool = Pool(processes=(cpu_count()))
    tmp_file_num = 0

    #num_nodes = [16, 64, 256, 1024]
    #num_nodes = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
    num_nodes = [1]
    cache_sizes = [1]

    cvm_cold_boot_time = 8.3073
    cvm_warm_boot_time = 0.0677
    cvm_max_execution_slots = 1
    cvm_header = "************* CVM ****************\n"

    vm_cold_boot_time = 3.6999
    vm_warm_boot_time = 0.0663
    vm_max_execution_slots = 1
    vm_header = "************* VM ****************\n"

    w_percentage_soft_warm = [0, 0.3, 0.6]
    w_cold_boot_time = 4.3061
    w_warm_boot_time = 1.6766
    w_soft_warm_time = 2.4124
    w_max_execution_slots = 1
    w_header = "************* WALLET ****************\n"

    #main_sim(1, vm_cold_boot_time, vm_warm_boot_time, 0, 1, 300, vm_max_execution_slots, 0);

    for n in num_nodes:
        for cache_size in cache_sizes:
            # CVM simulation
            pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', cvm_header, n, cvm_cold_boot_time, cvm_warm_boot_time, 0, cache_size, 300, cvm_max_execution_slots, 0))
            tmp_file_num += 1

            # VM simulation
            pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', cvm_header, n, vm_cold_boot_time, vm_warm_boot_time, 0, cache_size, 300, vm_max_execution_slots, 0))
            tmp_file_num += 1

            # Wallet simulation
            for percent_soft_warm in w_percentage_soft_warm:
                pool.apply_async(proc, args=(f'tmp_file_{tmp_file_num}.txt', w_header, n, w_cold_boot_time, w_warm_boot_time, w_soft_warm_time, cache_size, 300, w_max_execution_slots, percent_soft_warm))
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


