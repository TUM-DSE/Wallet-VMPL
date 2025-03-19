#include <stdio.h>
#include <stdlib.h>
#include <sys/io.h>
#include "cpuid.c"

int main() {

  int* a = malloc(64);
  fprintf(stderr, "Before finalize: %p", a);

  __asm__ volatile("mov $0x4FFFFFF4, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");

  fprintf(stderr, "After finalize");
  *a = 5;

  fprintf(stderr, "Test print");
  notify_monitor();

  fprintf(stderr, "Second try");
  trustlet_exit();

  return 0;
}
