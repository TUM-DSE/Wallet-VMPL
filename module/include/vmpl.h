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
    invokeTrustlet = 8,
    waitForTrustletResult,

	get_public_key = 30,
	send_policy = 31,
	execute_elf = 32,

    create_data_struct = 50,
};

// A Zygote consists of the PAL, the Manifest and the LibOS

struct monitor_call {
    enum monitor_call_type type;
    union {
        int vmpl_level;
        struct mem memory;
        tpid_t process_id;
        struct /* monitor attestation */ {
            void* address;
            uint64_t type; 
        } monitor_attestation;
        void* attestation_target;
        struct /* invokation */ {
            tpid_t process_id;
            void* input_data;
            uint64_t input_data_size;
            void* result;
            uint64_t result_size;
        }invokation;
        struct /* zygote */ {
            void* zygote_data;
            uint64_t size;
        }zygote;
        struct /* trustlet */ {
            void* trustlet_data;
            uint64_t size;
            tpid_t zygote;
        }trustlet;
        struct /* decryption_context */ {
            void* sender_pub_key;
            void* encrypted_data;
            uint32_t encrypted_data_size;
        }decryption_context;
        struct /* execute_elf_contexti */ {
            void* page1;
            void* page2;
            uint32_t size;
        }execute_elf_context;
        struct /* data_info */ {
            void* start_address;
            uint64_t size; //In 4K pages
        }data_info;
    };
};

#define VMPL_WR _IOR('a','a',struct monitor_call)

#endif
