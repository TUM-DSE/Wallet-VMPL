#ifndef VMPL_H
#define VMPL_H

typedef uint64_t tpid_t;

struct mem {
    void* stack;
    void* pages;
    void* vmsa;
};

enum monitor_call_type {
    initMonitor = 0,
    attestMonitor = 1,
    attest, 
    loadPolicy,
    createZygote,
    deleteZygote,
    createTrustlet,
    deleteTrustlet,
    invokeTrustlet,
    waitForTrustletResult,

	get_public_key = 30,
};

struct monitor_call {
    enum monitor_call_type type;
    union {
        int vmpl_level;
        struct mem memory;
        struct{
            void* address;
            uint64_t type; 
        }monitor_attestation;
        void* attestation_target;
        tpid_t process_id;
        struct zygote {
            void* zygote;
            uint32_t size; 
        }zygote;
        struct trustlet {
            void* trustlet_data;
            uint32_t size;
            tpid_t zygote;
        }trustlet;
    };
};

#define VMPL_WR _IOR('a','a',struct monitor_call)

#endif
