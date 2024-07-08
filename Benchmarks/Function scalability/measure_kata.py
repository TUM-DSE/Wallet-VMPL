 
import os

def start():
    file = "measurements.txt"
    f = open(file, "a")
    for i in range(1, 301):
        os.system(f"(echo \"[Running {i} functions]\" >&2) &>> {file}")
        for j in range(10):
            os.system(f"(time parallel -j {i} -N0 docker run --runtime=kata-qemu outb ::: {{1..{i}}}) &>> {file}")
if __name__ == '__main__':
    start()
