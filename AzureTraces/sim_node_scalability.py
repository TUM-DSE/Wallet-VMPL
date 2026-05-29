from simulate import main_sim
from multiprocessing import Pool, cpu_count
import sys
import os


def proc(output_file, header, total_cores, cold_start_time, cold_start_std,
         reschedule_time, reschedule_std, concurrent_per_vnf, cores_per_chain,
         max_vms, pbar_position, input_file):
    import traceback
    f = open(output_file, "w")
    f.write(header)
    old_stdout = sys.stdout
    sys.stdout = f
    try:
        main_sim(total_cores, cold_start_time, cold_start_std,
                 reschedule_time, reschedule_std,
                 concurrent_per_vnf, cores_per_chain, max_vms,
                 pbar_position, input_file)
    except Exception as e:
        sys.stdout = old_stdout
        traceback.print_exc()
        raise
    finally:
        sys.stdout = old_stdout
        f.close()


def error_callback(e):
    import traceback
    traceback.print_exception(type(e), e, e.__traceback__)

def main():
    pool = Pool(processes=cpu_count())
    tmp_file_num = 0
    input_file = sys.argv[1]

    # total_cores_list = [128+64] # for 500
    total_cores_list = [ 512, 1024, 2048, 4096 ] # for 4000
    # total_cores_list = [ 256 ] # for 4000
    cores_per_chain = 3
    cores_per_server = 64
    cvm_max_vms_per_server = 512

    # Containers
    container_cold_start = 11.0          # 11.0s
    container_cold_std = 0.1 * container_cold_start
    container_reschedule = 0.000004     # 4us
    container_reschedule_std = 0.1 * container_reschedule
    container_concurrent = 32 * 128 # In wallet we expect 16 requests per trustlet on average
    container_max_vms = 0
    container_header = "************* CONTAINERS ****************\n"

    # VMs
    vm_cold_start = 37.9
    vm_cold_std = 0.1 * vm_cold_start
    vm_reschedule = 0.000005            # 5us
    vm_reschedule_std = 0.1 * vm_reschedule
    vm_concurrent = 16 * 20
    vm_max_vms = 0
    vm_header = "************* VM ****************\n"

    # CVMs
    cvm_cold_start = 11.0
    cvm_cold_std = 0.1 * cvm_cold_start
    cvm_reschedule = 0.000007           # 7us
    cvm_reschedule_std = 0.1 * cvm_reschedule
    cvm_concurrent = 16 * 16
    cvm_header = "************* CVM ****************\n"

    # Slick
    slick_cold_start = 31.5
    slick_cold_std = 0.1 * slick_cold_start
    slick_reschedule = 0.000073         # 16us
    slick_reschedule_std = 0.1 * slick_reschedule
    slick_concurrent = 128 * 80000
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
            tmp_file_num, input_file), error_callback=error_callback)
        tmp_file_num += 1

        # VMs
        pool.apply_async(proc, args=(
            f'tmp_file_{tmp_file_num}.txt', vm_header,
            total_cores, vm_cold_start, vm_cold_std,
            vm_reschedule, vm_reschedule_std,
            vm_concurrent, cores_per_chain, vm_max_vms,
            tmp_file_num, input_file), error_callback=error_callback)
        tmp_file_num += 1

        # CVMs
        num_servers = total_cores // cores_per_server
        cvm_max_vms = num_servers * cvm_max_vms_per_server
        pool.apply_async(proc, args=(
            f'tmp_file_{tmp_file_num}.txt', cvm_header,
            total_cores, cvm_cold_start, cvm_cold_std,
            cvm_reschedule, cvm_reschedule_std,
            cvm_concurrent, cores_per_chain, cvm_max_vms,
            tmp_file_num, input_file), error_callback=error_callback)
        tmp_file_num += 1

        # Slick
        pool.apply_async(proc, args=(
            f'tmp_file_{tmp_file_num}.txt', slick_header,
            total_cores, slick_cold_start, slick_cold_std,
            slick_reschedule, slick_reschedule_std,
            slick_concurrent, cores_per_chain, slick_max_vms,
            tmp_file_num, input_file), error_callback=error_callback)
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
