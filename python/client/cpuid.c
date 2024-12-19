

void notify_monitor(){

    __asm__ volatile("mov $0x4FFFFFF8, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");

}
