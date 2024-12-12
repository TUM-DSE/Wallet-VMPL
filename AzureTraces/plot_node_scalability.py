import csv
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.pyplot as plt

def convert_txt_to_array(text):
    text_values = text[1:-1]
    values = [float(i) for i in text_values.split(',')]
    return values

def plot_node_scalability():
    input_file = 'node_scalability.csv'
    with open(input_file, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=';')
        header = next(reader)  # Read the header row
        values = [row for row in reader]
    
    num_nodes = convert_txt_to_array(values[0][0])
    vm_results = convert_txt_to_array(values[0][1])
    cvm_results = convert_txt_to_array(values[0][2])
    w_results = convert_txt_to_array(values[0][3])
    
    plt.title("Lower is better ↓", fontsize=9, color="navy", weight="bold")
    plt.xlabel("Num nodes")
    plt.ylabel("Execution time (s)")
    plt.plot(num_nodes, vm_results, label = 'VM')
    plt.plot(num_nodes, cvm_results, label = 'CVM')
    plt.plot(num_nodes, w_results, label = 'Wallet')
    plt.legend()
    plt.grid()
#x_ticks = np.linspace(0, 1024, 5, dtype=int)
#plt.xticks(x_ticks, (str(i) for i in x_ticks))

    plt.savefig('mock_overhead.png', format='png', dpi=1200)
    plt.show()

    print(num_nodes)
    print(vm_results)
    print(cvm_results)
    print(w_results)

if __name__ == '__main__':
    plot_node_scalability()
# context size
#x_axis = np.array([16, 32, 64, 128, 256, 512, 1024])

# ms/token
#native = np.array([2, 3, 5, 7, 9, 12, 15])
#virt = np.array([4, 5, 7, 9, 11, 14, 17])
#trust = np.array([5, 6, 8, 10, 12, 15, 18])

#plt.title("LLM-OS overhead")
#plt.title("Lower is better ↓", fontsize=9, color="navy", weight="bold")
#plt.xlabel("Context size (tokens)")
#plt.ylabel("Inference latency (ms/token)")
#plt.plot(x_axis_new, native_smooth, label = 'Native')
#plt.plot(x_axis_new, virt_smooth, label = 'Virtualized')
#plt.plot(x_axis_new, trust_smooth, label = 'LLM-OS')
#plt.legend()
#plt.grid()
#x_ticks = np.linspace(0, 1024, 5, dtype=int)
#plt.xticks(x_ticks, (str(i) for i in x_ticks))

#plt.savefig('mock_overhead.png', format='png', dpi=1200)
#plt.show()

