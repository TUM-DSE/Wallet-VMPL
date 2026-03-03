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
    createChannel,
    deleteChannel,

    get_public_key = 30,
    send_policy = 31,
    execute_elf = 32,

    create_data_struct = 50,

    get_stat = 100,
    reset_stat = 101,

    createSharedMemory = 102,
    deleteSharedMemory = 103,
};

enum attestation_report_type {
    monitorAttestation = 0,
    zygoteAttestation = 1,
    trustletAttestation = 2,
    functionAttestation = 3,
    /* helper attestation options for microbenchmarks */
    monitorAttestationCold = 4,
    prepareZygoteAttestationCold = 5,
    zygoteAttestationCold = 6,
    prepareTrustletAttestationCold = 7,
    trustletAttestationCold = 8,
    /* end of helper attestation options for microbenchmarks */
    maxAttestationReportType,
};


// A Zygote consists of the PAL, the Manifest and the LibOS

/* Structure of function data is shown below */
// typedef struct PACKED _function_data {
//   uint64_t trustletId; // 8 bytes
//   uint64_t fnInputSize; // 8 bytes
//   void* fnInput; // 8 bytes
//   uint64_t fnOutputSize; // 8 bytes
//   void* fnOutput; // 8 bytes
// } function_data;

struct monitor_call {
    enum monitor_call_type type;
    union {
        int vmpl_level;
        struct mem memory;
        tpid_t process_id;
        struct /* monitor attestation */ {
            void* address;
            uint64_t process_id;
            void* function_data_ptr;
            enum attestation_report_type type;
        } monitor_attestation;
        void* attestation_target; /* contains the buffer to store the result */
        struct {
            tpid_t process_id;
            void* data;
            uint64_t data_size;
        } invokation;
        struct {
            void* zygote_data;
            uint64_t size;
            uint64_t privileged;
        } zygote;
        struct {
            void* trustlet_data;
            uint64_t size;
            tpid_t zygote;
        } trustlet;
        struct {
            void* sender_pub_key;
            void* encrypted_data;
            uint32_t encrypted_data_size;
        } decryption_context;
        struct /* execute_elf_contexti */ {
            void* page1;
            void* page2;
            uint32_t size;
        } execute_elf_context;
        struct {
            void* start_address;
            uint64_t size; //In 4K pages
        } data_info;
        struct {
            tpid_t trustlet_id_1;
            tpid_t trustlet_id_2;
        } channel;
        struct {
            tpid_t trustlet_id;
            void* guest_buffer;
            uint64_t size;
        } shared_memory;
    };
};

#define VMPL_WR _IOR('a','a',struct monitor_call)

/* Attestation related defs */
// NOTE: used for testing for now
#define MAX_PATH_SIZE 256
#define MONITOR_ATTESTATION_REPORT_PATH "monitor_attestation_report"
#define ZYGOTE_ATTESTATION_REPORT_PATH "zygote_attestation_report"
#define TRUSTLET_ATTESTATION_REPORT_PATH "trustlet_attestation_report"
#define FUNCTION_ATTESTATION_REPORT_PATH "function_attestation_report"

typedef struct {
    const char *name;
    size_t offset;
    size_t size; // in bytes
} Field;

static Field fields[] = {
    {"VERSION", 0x00, 4},
    {"GUEST_SVN", 0x04, 4},
    {"POLICY", 0x08, 8},
    {"FAMILY_ID", 0x10, 16},
    {"IMAGE_ID", 0x20, 16},
    {"VMPL", 0x30, 4},
    {"SIGNATURE_ALGO", 0x34, 4},
    {"CURRENT_TCB", 0x38, 8},
    {"PLATFORM_INFO", 0x40, 8},
    {"SIGNING_KEY", 0x48, 1},
    {"MASK_CHIP_KEY", 0x48, 1}, // Overlapping with SIGNING_KEY
    {"AUTHOR_KEY_EN", 0x48, 1}, // Overlapping with MASK_CHIP_KEY
    {"RESERVED", 0x4C, 4},
    {"REPORT_DATA", 0x50, 64},
    {"MEASUREMENT", 0x90, 48},
    {"HOST_DATA", 0xC0, 32},
    {"ID_KEY_DIGEST", 0xE0, 48},
    {"AUTHOR_KEY_DIGEST", 0x110, 48},
    {"REPORT_ID", 0x140, 32},
    {"REPORT_ID_MA", 0x160, 32},
    {"REPORTED_TCB", 0x180, 8},
    {"CPUID_FAM_ID", 0x188, 1},
    {"CPUID_MOD_ID", 0x189, 1},
    {"CPUID_STEP", 0x18A, 1},
    {"CHIP_ID", 0x1A0, 64},
    {"COMMITTED_TCB", 0x1E0, 8},
    {"CURRENT_BUILD", 0x1E8, 1},
    {"CURRENT_MINOR", 0x1E9, 1},
    {"CURRENT_MAJOR", 0x1EA, 1},
    {"COMMITTED_BUILD", 0x1EC, 1},
    {"COMMITTED_MINOR", 0x1ED, 1},
    {"COMMITTED_MAJOR", 0x1EE, 1},
    {"LAUNCH_TCB", 0x1F0, 8},
    {"SIGNATURE", 0x2A0, 512},
    {"INIT_MEASUREMENT", 0x4A0, 64},           // Wallet differential attestation field
    {"MANIFEST_MEASUREMENT", 0x4E0, 64},       // Wallet differential attestation field
    {"LIBOS_MEASUREMENT", 0x520, 64},          // Wallet differential attestation field
    {"FUNCTION_MEASUREMENT", 0x560, 64},       // Wallet differential attestation field
    {"FUNCTION_INPUT_MEASUREMENT", 0x5A0, 64}, // Wallet differential attestation field
    {"FUNCTION_OUTPUT_MEASUREMENT", 0x5E0, 64},// Wallet differential attestation field
    {"WALLET_SIGNATURE", 0x620, 64}            // Wallet differential attestation field
};
/* End of attestation dump-related defs */

#endif
