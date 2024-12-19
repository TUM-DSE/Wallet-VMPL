
int main() {
    asm volatile ("mov $123, %%rax; cpuid" : : : "%rax", "%rbx", "%rcx", "%rdx");
    return 0;
}
