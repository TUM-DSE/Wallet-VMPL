

void notify_monitor(){
    __asm__ volatile("mov $0x4FFFFFF8, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
}

void call_outb(){
    __asm__ volatile("mov $0x4FFFFFF7, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
}

void trustlet_exit() {
    __asm__ volatile("mov $0x4FFFFFF6, %%rax; cpuid":::"rax", "rbx", "rcx", "rdx");
}
