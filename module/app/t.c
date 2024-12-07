#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>

#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <stddef.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <threads.h>
#include <pthread.h> 
#include <sched.h>
#include <sys/mman.h>
#include <inttypes.h>
#include <stdlib.h>

typedef signed long long int u64;
#define  PACKED __attribute__((__packed__)) 
#include "vmpl.h"
#include "measurement_utils.h"
#include "my_crypto.h"
//#define rax 1
//#define rcx 2
//#define rdx 3
//#define r8 4
//#define r9 5
#define HASH_SIZE 64
struct svsm_call {
	void* caa;
	u64 rax;
	u64 rcx;
	u64 rdx;
	u64 r8;
	u64 r9;
};
struct PACKED attestation_report {
    uint32_t status;
    uint32_t report_size;
    uint8_t reserved[24];
    uint8_t pub_key_hash[HASH_SIZE];
    uint8_t report[];
};

typedef struct PACKED _policy {
	uint8_t zygote_hash[HASH_SIZE];
	uint8_t trustlet_hash[HASH_SIZE];
	uint8_t data[4096 / 2 - 2 * HASH_SIZE + 400]; // TODO: For now policy is constrained to 1 page
} policy;

// this struct is allocated with alignment requirements!
typedef struct PACKED _function_data {
  uint64_t trustletId; // 8 bytes
  uint64_t fnInputSize; // 8 bytes
  void* fnInput; // 8 bytes
  uint64_t fnOutputSize; // 8 bytes
  void* fnOutput; // 8 bytes
  void* reportOutput;
} function_data;

struct mem memory;
int fd;

void load_file(const char* filename, uint8_t** buffer, uint64_t* buffer_size);

// Function to print the buffer as hex
void print_buffer_hex(FILE *file, const uint8_t *buffer, size_t size) {
    for (size_t i = 0; i < size; i++) {
        fprintf(file, "%02X", buffer[i]);
        if ((i + 1) % 16 == 0) fprintf(file, "\n"); // Line break every 16 bytes
    }
    if (size % 16 != 0) fprintf(file, "\n"); // Final line break if not multiple of 16
}

// Function to parse and print the attestation report
void print_attestation_report(const uint8_t *att_buffer, FILE *file) {
    size_t field_count = sizeof(fields) / sizeof(fields[0]);
    for (size_t i = 0; i < field_count; i++) {
        const Field *field = &fields[i];
        fprintf(file, "%s (Offset: 0x%02lX, Size: %lu bytes):\n",
                field->name, field->offset, field->size);
        print_buffer_hex(file, att_buffer + field->offset, field->size);
        fprintf(file, "\n");
    }
}

int call_attest(uint8_t* pub_key_hash) {
    u64 page_size = sysconf(_SC_PAGESIZE);
    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
    att_buffer[0] = 1;
    for(int i = 0; i < page_size;i++){
        att_buffer[i] = i % 200;
    }

    cpu_set_t cpuset;
    struct monitor_call call;
    call.attestation_target = att_buffer;
    u64 ret;
    call.type = attest;
    call.monitor_attestation.type = monitorAttestation;
    ret = ioctl(fd, VMPL_WR, &call);

    struct attestation_report* report = (struct attestation_report*)att_buffer;

    // Open a file for writing the report
    FILE *output_file = fopen(MONITOR_ATTESTATION_REPORT_PATH, "w");
    if (output_file == NULL) {
        perror("Error opening file");
        return 1;
    }
    print_attestation_report(att_buffer, output_file);
	  // Extract pub key hash
	  memcpy(pub_key_hash, att_buffer + 112, 64);

    free(att_buffer);

    // Close the output file
    fclose(output_file);
}

void get_pub_key(uint8_t* key) {
    u64 page_size = sysconf(_SC_PAGESIZE);
    uint8_t* key_buffer = aligned_alloc(page_size, page_size);
    key_buffer[0] = 0;
    struct monitor_call call;
    call.attestation_target = key_buffer;
    u64 ret;
    call.type = get_public_key;
    ret = ioctl(fd,VMPL_WR,&call);

    printf("Key buff: [");
    for(int i = 0; i < 32; i++) {
        printf("%d ", key_buffer[i]);
    }
    printf("]\n");
    // find size of key
    memcpy(key, key_buffer, 32);

    free(key_buffer);
}

void monitor_init() {
    struct monitor_call call;
    call.type = initMonitor;
    int ret = ioctl(fd,VMPL_WR,&call);
    printf("Init called\n");
}

void single_exec(){
    u64 page_size = sysconf(_SC_PAGESIZE);
    struct monitor_call call; 
    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
    call.trustlet.size = 1;
    call.trustlet.trustlet_data = att_buffer;
    call.trustlet.zygote = 1;
    call.type = createTrustlet;
    int ret = ioctl(fd,VMPL_WR,&call);
    printf("Init called\n");
    free(att_buffer);
}

struct zygote_data {
    void* zygote_data[3];
    uint64_t size[3];
};

void allocate_zygote_struct(struct zygote_data** z){
    u64 page_size = sysconf(_SC_PAGESIZE);
    uint8_t* buf = aligned_alloc(page_size, page_size);
    for(int i = 0; i < page_size; i++)
        buf[i] = 0;
    *z = (void*)buf;
}

int create_zygote(const char* zygote){
    printf("Trying to register Zygote with Monitor");
    uint8_t* data;
    uint64_t size;
    load_file(zygote, &data, &size);
    printf("Zygote(%s) size: %ld\n", zygote, size);

    uint8_t* manifest;
    uint64_t manifest_size;
    load_file("manifest", &manifest, &manifest_size);
   
    uint8_t* libos;
    uint64_t libos_size;
    load_file("libsysdb.so", &libos, &libos_size);

    struct zygote_data* z;
    allocate_zygote_struct(&z);
    z->zygote_data[0] = data;
    z->size[0] = size;
    z->zygote_data[1] = manifest;
    z->size[1] = manifest_size;
    z->zygote_data[2] = libos;
    z->size[2] = libos_size;

    struct monitor_call call;
    /*call.zygote.zygote_data[0] = data;
    call.zygote.size[0] = size;
    call.zygote.zygote_data[1] = manifest;
    call.zygote.size[1] = manifest_size;
    */

    u64 page_size = sysconf(_SC_PAGESIZE);
    call.zygote.zygote_data = (void*)z;
    call.zygote.size = page_size;

    call.type = createZygote;

    int ret = ioctl(fd, VMPL_WR,&call);

    printf("Zygote ID: %d\n",ret);
    return ret;
}

int create_trustlet(const int zygote_id) {
    printf("Trying to register Trustlet with Monitor\n");

    struct monitor_call call;
    call.type = createTrustlet;
    call.trustlet.zygote = zygote_id;

    int ret = ioctl(fd, VMPL_WR, &call);

    printf("Trustlet ID: %d\n", ret);
    return ret;
}

int invoke_trustlet(const int trustlet_id) {
    printf("Trying to invoke Trustlet\n");

    struct monitor_call call;
    call.type = invokeTrustlet;
    call.process_id = trustlet_id;

    int ret = ioctl(fd, VMPL_WR, &call);
}


static void _send_policy (uint8_t* encrypted_policy, uint8_t* sender_pub_key) {
    struct monitor_call call;
    call.decryption_context.sender_pub_key = sender_pub_key;
    call.decryption_context.encrypted_data = encrypted_policy;
    call.decryption_context.encrypted_data_size = sizeof(policy) + 16;
    u64 ret;
    call.type = send_policy;
    ret = ioctl(fd,VMPL_WR,&call);
    //printf("ret = %lld\n", ret);
}

void load_file(const char* filename, uint8_t** buffer, uint64_t* buffer_size){
    u64 page_size = sysconf(_SC_PAGESIZE);
    FILE* file = fopen(filename,"r");
    fseek(file, 0L, SEEK_END);
    uint64_t size = ftell(file);
    rewind(file);
    uint8_t* buf = aligned_alloc(page_size, size + page_size);
    for(int i = 0; i < size + page_size; i++)
        buf[i] = 0;
    size_t read_len = fread((void*)buf,1,size,file);
    if(read_len != size){
        fprintf(stderr,"Failed to load entire file %ld != %ld", read_len, size);
        exit(-1);
    }
    fprintf(stderr, "Start Address: %p\n", buf);
    *buffer = buf;
    *buffer_size = size;
}

static long load_elf(){
    printf("test");
    uint8_t* data;
    uint64_t size;
    load_file("libpal.so", &data, &size);
    //load_file("simple_elf",&data,&size);

    printf("\nStart Address: %p, First bytes: %d\n", data,data[0]);
    printf("Size %ld\n",size);
    uint64_t sum = 0;
    struct monitor_call call;
    call.data_info.size = size;
    call.data_info.start_address = data;
    call.type = create_data_struct;
    ioctl(fd, VMPL_WR, &call);
}

static long exec_elf(const unsigned char* filename, int* argument)
{
	// Map ELF file to memory
	FILE* file = fopen(filename, "r");
	fseek(file, 0L, SEEK_END);
	long size = ftell(file);
  u64 page_size = sysconf(_SC_PAGESIZE);

  if(size > page_size * 2) {
		  printf("Error: we only support 2 page elf at this point\n");
		  return -1;
	}

	rewind(file);
	printf("Size of file: %ld\n", size);
	void* file_contents = mmap(NULL, size, PROT_EXEC | PROT_READ, MAP_PRIVATE,
			fileno(file), 0);

	if(file_contents == MAP_FAILED) {
		  printf("Failed mapping the file");
		  return -1;
	}
	printf("File successfully mapped: %p !\n", file_contents);


	unsigned char* file_raw = (unsigned char*)file_contents;
	printf("Raw file bytes: [");
	for(int i = 0; i < size; i++) {
		  printf("%d ", file_raw[i]);
	}
	printf("]\n");

	sleep(3);

	uint8_t* page1 = aligned_alloc(page_size, page_size);
	uint8_t* page2 = aligned_alloc(page_size, page_size);
	page1[0] = 0;
	page2[0] = 0;

	memcpy(page1, file_contents, page_size);
	memcpy(page2, file_contents + page_size, size - page_size);
	
	struct monitor_call call;
	call.execute_elf_context.page1 = page1;
	call.execute_elf_context.page2 = page2;
	call.execute_elf_context.size = size;
	call.type = execute_elf;
	u64 ret;
	ret = ioctl(fd, VMPL_WR, &call);
	sleep(1);
}

static inline int attestation(policy* p, uint8_t* encrypted_policy, key_pair* keys, uint8_t* public_key) 
{
	uint8_t pub_key_hash[HASH_SIZE];
	uint8_t hash[HASH_SIZE];

	call_attest(pub_key_hash);
	uint8_t key[32];
	get_pub_key(key);

	if(key == NULL) {
		  printf("Could not get key!!\n");
	} else {
		  printf("Monitor public key: [");
		  for(int i = 0; i < 32; i++) {
			    printf("%d ", key[i]);
		  }
		  printf("]\n");
	}

	my_SHA512(key, 32, hash);

	if(memcmp(pub_key_hash, hash, HASH_SIZE) == 0) {
		  //printf("The hashes match!!\n");
	} else {
		  printf("The hashes don't match :(\n");
	}
	 
	uint8_t nonce[24] = {0};
	int n = encrypt(encrypted_policy, (uint8_t*)p, sizeof(policy), nonce, key, keys->private_key);	
	
	_send_policy(encrypted_policy, public_key);

	return 0;
}

key_pair* prepair_keys(){
    key_pair* keys = gen_keys();
    printf("Hacl Private key: [");
    for(int i = 0; i < 32; i++) {
        printf("%02x", keys->private_key[i]);
    }
    printf("]\n");
    printf("Hacl Public key:  [");
    for(int i = 0; i < 32; i++) {
        printf("%02x", keys->public_key[i]);
    }
    printf("]\n");
    return keys;
}

policy* prepair_policy(){
    policy* p = (policy*)malloc(sizeof(policy));
    if(p == NULL) {
        printf("Can't allocate p\n");
        exit(-1);
    }
    p->zygote_hash[0] = 233;
    p->trustlet_hash[0] = 244;
    p->data[0] = 250;
    p->data[300] = 69;
    p->data[2310] = 169;
    printf("Size of policy: %ld\n", sizeof(policy));
    return p;
}

void attestation_time(key_pair* keys, policy* p){
     u64 page_size = sysconf(_SC_PAGESIZE);
     uint8_t* encrypted_policy = aligned_alloc(page_size, page_size);
     if(encrypted_policy == NULL) {
         printf("Can't allocate encrypted_policy\n");
         exit(-1);
     }
     encrypted_policy[0] = 0;
     uint8_t* public_key = aligned_alloc(page_size, page_size);
     memcpy(public_key,(uint8_t*)keys,32);
     double total = 0.0;
     const int iterations = 1;
     monitor_init();
     for(int i = 0; i < iterations; i++){
         uint64_t start = get_cycles();
         attestation(p, encrypted_policy, keys, public_key);
         uint64_t end = get_cycles();
         total += (end - start)/iterations;
     }
     printf("Attestation time: %f\n", cycles_to_ms(total, get_CPU_freq()));
     printf("Decryption took %f ms\n", cycles_to_ms(1635596, get_CPU_freq()));
}

int attest_monitor(key_pair* keys, policy* p){
    u64 page_size = sysconf(_SC_PAGESIZE);

    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
    if (att_buffer == NULL) {
        printf("Can't allocate monitor attestation report buffer\n");
        return -1;
    }
    for(int i = 0; i < page_size; i++){
        att_buffer[i] = 0; // i % 200;
    }

    struct monitor_call call;
    call.type = attest;
    call.attestation_target = att_buffer;
    call.monitor_attestation.type = monitorAttestation;
    u64 ret = ioctl(fd, VMPL_WR, &call);

    struct attestation_report* report = (struct attestation_report*)att_buffer;

    // Open a file for writing the report
    FILE *output_file = fopen(MONITOR_ATTESTATION_REPORT_PATH, "w");
    if (output_file == NULL) {
        perror("Error opening file");
        return 1;
    }
    print_attestation_report(att_buffer, output_file);
    free(att_buffer);
    // Close the output file
    fclose(output_file);

    return 0;
}

int attest_zygote(const int zygote_id, key_pair* keys, policy* p){
    u64 page_size = sysconf(_SC_PAGESIZE);

    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
    if (att_buffer == NULL) {
        printf("Can't allocate zygote attestation report buffer\n");
        return -1;
    }
    for(int i = 0; i < page_size; i++){
        att_buffer[i] = 0; //i % 200;
    }

    struct monitor_call call;
    call.type = attest;
    call.attestation_target = att_buffer;
    call.monitor_attestation.type = zygoteAttestation;
    call.monitor_attestation.process_id = zygote_id;
    u64 ret = ioctl(fd, VMPL_WR, &call);

    struct attestation_report* report = (struct attestation_report*)att_buffer;
    // Open a file for writing the report
    FILE *output_file = fopen(ZYGOTE_ATTESTATION_REPORT_PATH, "w");
    if (output_file == NULL) {
        perror("Error opening file");
        return 1;
    }
    print_attestation_report(att_buffer, output_file);
    free(att_buffer);
    // Close the output file
    fclose(output_file);
    return 0;
}

int attest_trustlet(const int trustlet_id, key_pair* keys, policy* p){
    u64 page_size = sysconf(_SC_PAGESIZE);

    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
    if (att_buffer == NULL) {
        printf("Can't allocate trustlet attestation report buffer\n");
        return -1;
    }
    for(int i = 0; i < page_size; i++){
        att_buffer[i] = 0; //i % 200;
    }

    struct monitor_call call;
    call.type = attest;
    call.attestation_target = att_buffer;
    call.monitor_attestation.type = trustletAttestation;
    call.monitor_attestation.process_id = trustlet_id;
    u64 ret = ioctl(fd, VMPL_WR, &call);

    struct attestation_report* report = (struct attestation_report*)att_buffer;
    // Open a file for writing the report
    FILE *output_file = fopen(TRUSTLET_ATTESTATION_REPORT_PATH, "w");
    if (output_file == NULL) {
        perror("Error opening file");
        return 1;
    }
    print_attestation_report(att_buffer, output_file);
    free(att_buffer);
    // Close the output file
    fclose(output_file);
    return 0;
}

int attest_function(function_data* function_data_ptr, const int trustlet_id, key_pair* keys, policy* p){
    u64 page_size = sysconf(_SC_PAGESIZE);

    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
    if (att_buffer == NULL) {
        printf("Can't allocate trustlet attestation report buffer\n");
        return -1;
    }
    for(int i = 0; i < page_size; i++){
        att_buffer[i] = 0; //i % 200;
    }

    struct monitor_call call;
    call.type = attest;
    call.attestation_target = att_buffer;
    call.monitor_attestation.type = functionAttestation;
    call.monitor_attestation.process_id = trustlet_id;
    call.monitor_attestation.function_data_ptr = (void*)function_data_ptr;
    u64 ret = ioctl(fd, VMPL_WR, &call);

    struct attestation_report* report = (struct attestation_report*)att_buffer;
    FILE *output_file = fopen(FUNCTION_ATTESTATION_REPORT_PATH, "w");
    if (output_file == NULL) {
        perror("Error opening file");
        return 1;
    }
    print_attestation_report(att_buffer, output_file);
    free(att_buffer);
    // Close the output file
    fclose(output_file);
    return 0;
}

void allocate_function_struct(function_data** fn){
    u64 page_size = sysconf(_SC_PAGESIZE);
    uint8_t* buf = aligned_alloc(page_size, page_size);
    for(int i = 0; i < page_size; i++)
        buf[i] = 0;
    *fn = (void*)buf;
}

int main(int argc, char** argv)
{
    int test_num = 0;
    if (argc > 1) {
        test_num = atoi(argv[1]);
    }
    printf("Test number: %d\n", test_num);

    // Set affinity to CPU 2
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(2, &cpuset);
    pthread_t thread = pthread_self();
    int pr = pthread_setaffinity_np(thread, sizeof(cpu_set_t), &cpuset);

    fd = open("/dev/vmpl_device", O_RDWR);
    if(fd < 0) {
        printf("Cannot open device file...\n");
        return -1;
    }

    switch (test_num) {
        case 0: {
            // OK
            printf("Trustlet test\n");
            create_zygote("libpal.so");
            create_trustlet(0);
            invoke_trustlet(1);
            break;
        }
        case 1: {
            // not work
            printf("Multiple execution test\n");
            create_zygote("libpal.so");
            create_trustlet(0);
            invoke_trustlet(1);
            invoke_trustlet(1);
            break;
        }
        case 2: {
            // not work
            printf("Multiple execution test2\n");
            create_zygote("libpal.so");
            create_trustlet(0);
            invoke_trustlet(1);
            create_trustlet(0);
            invoke_trustlet(2);
            break;
        }
        case 3: {
            // OK
            printf("Multiple execution test3\n");
            create_zygote("libpal.so");
            create_trustlet(0);
            invoke_trustlet(1);

            create_zygote("libpal.so");
            create_trustlet(2);
            invoke_trustlet(3);
            break;
        }
        case 10: {
            printf("----- Differential attestation test -----\n");
            int ret = 0;

            printf("Preparing keys and policy\n");
            key_pair* keys = prepair_keys();
            policy* p = prepair_policy();

            printf("Initializing monitor\n");
            monitor_init();

            printf("Retrieving base monitor attestation report\n");
            ret = attest_monitor(keys, p);
            if (ret != 0)
              printf("Error in attesting monitor\n");
            printf("Monitor attestation report stored in %s\n", MONITOR_ATTESTATION_REPORT_PATH);

            printf("Creating Zygote\n");
            int zygote_id = create_zygote("libpal.so");

            printf("Attesting Zygote %d\n", zygote_id);
            ret = attest_zygote(zygote_id, keys, p);
            if (ret != 0)
              printf("Error in attesting zygote\n");
            printf("Zygote attestation report stored in %s\n", ZYGOTE_ATTESTATION_REPORT_PATH);

            printf("Creating Trustlet\n");
            int trustlet_id = create_trustlet(zygote_id);

            printf("Attesting Trustlet %d\n", trustlet_id);
            ret = attest_trustlet(trustlet_id, keys, p);
            if (ret != 0)
              printf("Error in attesting trustlet\n");
            printf("Trustlet attestation report stored in %s\n", TRUSTLET_ATTESTATION_REPORT_PATH);

            uint8_t input[512];
            uint64_t input_len = 512;
            uint8_t output[256];
            uint64_t output_len = 256;
            for (int i = 0; i < input_len ; i++) {
              input[i] = i;
            }
            for (int i = 0; i < output_len ; i++) {
              output[i] = input_len + i;
            }

            function_data* function_data_ptr;
            allocate_function_struct(&function_data_ptr);

            function_data_ptr->trustletId = trustlet_id;
            function_data_ptr->fnInput = (void*)input;
            function_data_ptr->fnInputSize = input_len;
            function_data_ptr->fnOutput = (void*)output;
            function_data_ptr->fnOutputSize = output_len;

            printf("Attesting Function based on trustlet %d\n", trustlet_id);
            ret = attest_function(function_data_ptr, trustlet_id, keys, p);
            if (ret != 0)
              printf("Error in attesting function\n");
            printf("Function attestation report stored in %s\n", FUNCTION_ATTESTATION_REPORT_PATH);
            free(function_data_ptr);
            break;
        }
        case 100+0: {
            printf("Attestation test\n");
            key_pair* keys = prepair_keys();
            policy* p = prepair_policy();
            attestation_time(keys,p);
            printf("Attestation report stored in %s\n", MONITOR_ATTESTATION_REPORT_PATH);
            break;
        }
        case 200+0: {
            printf("Single elf exec test\n");
            exec_elf("hello_elf_asm.elf", NULL);
            break;
        }
        default: {
            printf("Invalid test number! %d\n", test_num);
            break;
        }
    }

    close(fd);
    return 0;
}
