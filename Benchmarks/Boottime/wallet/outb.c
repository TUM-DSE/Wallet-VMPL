#include <stdio.h>
#include <stdlib.h>
#include <sys/io.h>

#define BENCHMARK_PORT 0xF4
#define LINUX_STARTUP_VALUE 100

static inline void outb_exec(int value) {

  if (ioperm(BENCHMARK_PORT, 1, 1)) {
    printf("Failed to get access to the benchmark port\n");
    return -1;
  }
  outb(value, BENCHMARK_PORT);
  return 0;
}

int main() {
  //For Zygote
  __asm__ volatile("mov $0x4FFFFFF4, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
  outb_exec(LINUX_STARTUP_VALUE);
  return 0;
}
