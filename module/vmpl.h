
struct mem {
    void* stack;
    void* pages;
    void* vmsa;
};

#define VMPL_WR _IOWR('a','a',struct svsm_call)
#define VMPL_W _IOW('a','b',u64)
#define VMPL_W2 _IOW('a','c',struct mem)