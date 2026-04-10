from simulate import main_sim
from multiprocessing import Pool, cpu_count
import sys
import os


def proc(output_file, header, total_cores, cold_start_time, cold_start_std,
         reschedule_time, reschedule_std, concurrent_per_vnf, cores_per_chain,
         max_vms, pbar_position, input_file):
    f = open(output_file, "w")
    f.write(header)
    with f as sys.stdout:
        main_sim(total_cores, cold_start_time, cold_start_std,
                 reschedule_time, reschedule_std,
                 concurrent_per_vnf, cores_per_chain, max_vms,
                 pbar_position, input_file)


def main():
    pool = Pool(processes=cpu_count())
    tmp_file_num = 0
    input_file = sys.argv[1]

    total_cores_list = [128+64] # for 500
    total_cores_list = [1024] # for 4000
    cores_per_chain = 3

    # Containers
    container_cold_start = 0.0033       # 3.3ms
    container_cold_std = 0.0
    container_reschedule = 0.000002     # 2us
    container_reschedule_std = 0.0
    container_concurrent = 32
    container_max_vms = 0
    container_header = "************* CONTAINERS ****************\n"

    # VMs
    vm_cold_start = 5.5
    vm_cold_std = 0.0
    vm_reschedule = 0.000008            # 8us
    vm_reschedule_std = 0.0
    vm_concurrent = 16
    vm_max_vms = 0
    vm_header = "************* VM ****************\n"

    # CVMs
    cvm_cold_start = 11.0
    cvm_cold_std = 0.0
    cvm_reschedule = 0.000040           # 40us
    cvm_reschedule_std = 0.0
    cvm_concurrent = 16
    cvm_max_vms = 512
    cvm_header = "************* CVM ****************\n"

    # Slick
    slick_cold_start = 3.5
    slick_cold_std = 0.0
    slick_reschedule = 0.000016         # 16us
    slick_reschedule_std = 0.0
    slick_concurrent = 128
    slick_max_vms = 0
    slick_header = "************* SLICK ****************\n"

    num_sims = len(total_cores_list) * 4
    print(f'Starting {num_sims} simulations')

    for total_cores in total_cores_list:
        # Containers
        pool.apply_async(proc, args=(
            f'tmp_file_{tmp_file_num}.txt', container_header,
            total_cores, container_cold_start, container_cold_std,
            container_reschedule, container_reschedule_std,
            container_concurrent, cores_per_chain, container_max_vms,
            tmp_file_num, input_file))
        tmp_file_num += 1

        # VMs
        pool.apply_async(proc, args=(
            f'tmp_file_{tmp_file_num}.txt', vm_header,
            total_cores, vm_cold_start, vm_cold_std,
            vm_reschedule, vm_reschedule_std,
            vm_concurrent, cores_per_chain, vm_max_vms,
            tmp_file_num, input_file))
        tmp_file_num += 1

        # CVMs
        pool.apply_async(proc, args=(
            f'tmp_file_{tmp_file_num}.txt', cvm_header,
            total_cores, cvm_cold_start, cvm_cold_std,
            cvm_reschedule, cvm_reschedule_std,
            cvm_concurrent, cores_per_chain, cvm_max_vms,
            tmp_file_num, input_file))
        tmp_file_num += 1

        # Slick
        pool.apply_async(proc, args=(
            f'tmp_file_{tmp_file_num}.txt', slick_header,
            total_cores, slick_cold_start, slick_cold_std,
            slick_reschedule, slick_reschedule_std,
            slick_concurrent, cores_per_chain, slick_max_vms,
            tmp_file_num, input_file))
        tmp_file_num += 1

    pool.close()
    pool.join()

    # Concatenate all temporary files into a single result file
    with open("simulation_results_parallel.txt", "w") as out:
        for i in range(tmp_file_num):
            infile_path = f'tmp_file_{i}.txt'
            with open(infile_path, 'r') as infile:
                out.write(infile.read())
            os.remove(infile_path)


if __name__ == '__main__':
    main()
