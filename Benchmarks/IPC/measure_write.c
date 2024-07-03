#include <sys/mman.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include <stdio.h>
#include <sys/time.h>
#include <string.h>

#define SHM_SIZE 4096
// from lspci 
#define SHM_BAR 0x700000000000 

int main() {
	int fd = open("/dev/mem", O_RDWR);
	if (fd == -1) {
		printf("Can't open file\n");
		return -1;
	}
	void *shm = mmap(NULL, SHM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, SHM_BAR);
	if (shm == MAP_FAILED) {
		printf("Can't map");
		return -1;
	}

	char data[4096] = {45, 100, 80, 114};

	long unsigned int total = 0;
	struct timeval start, end;

	for(int i = 0; i < 10000; i++) {
		gettimeofday(&start, NULL);
		memcpy(shm, data, 4096);
		gettimeofday(&end, NULL);


		total += (end.tv_sec - start.tv_sec) * 1000000 + end.tv_usec - start.tv_usec;
	}
	printf("took %f us\n", total/10000.0);
	munmap(shm, SHM_SIZE); 
	close(fd);
	printf("Program completed sucessfully\n");
	return 0;
}

