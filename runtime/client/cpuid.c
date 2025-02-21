#include <stdint.h>

void notify_monitor(){
    __asm__ volatile("mov $0x4FFFFFF8, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
}

void call_outb(){
    __asm__ volatile("mov $0x4FFFFFA0, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
}

void trustlet_exit() {
    __asm__ volatile("mov $0x4FFFFFA1, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
}

void call_outb_with_value(uint64_t value) {
   __asm__ volatile("mov $0x4FFFFFA2, %%rax; mov %0, %%rcx; cpuid":: "r" (value) :"rax", "rbx", "rcx", "rdx");
}

void resize_channel(uint64_t select, uint64_t size) {
    __asm__ volatile("mov $0x4FFFFFA1, %%rax; mov %0, %%rcx; mov %1, %%rdx; cpuid":: "r" (select), "r" (size):"rax", "rbx", "rcx", "rdx");
}

void nop(){
    __asm__ volatile("mov $0x4FFFFFF5, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
}
