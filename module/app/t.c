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
}policy;

struct mem memory;
int fd;



//uint8_t att_buffer[4096];
int call_attest(uint8_t* pub_key_hash) {
    u64 page_size = sysconf(_SC_PAGESIZE);
    uint8_t* att_buffer = aligned_alloc(page_size, page_size);
	att_buffer[0] = 1;
    for(int i = 0; i < page_size;i++){
        att_buffer[i] = i % 200;
    }
    //printf("p: %p\n",att_buffer);
    //sleep(1);
    cpu_set_t cpuset;
    struct monitor_call call;
    call.attestation_target = att_buffer;
    u64 ret;
    call.type = attest;
	call.monitor_attestation.type = 2;
    ret = ioctl(fd,VMPL_WR,&call);
    //printf("ret = %lld\n", ret);

    struct attestation_report* report = (struct attestation_report*)att_buffer;
    //FILE* report_file = fopen("/root/report.txt","w");
    //printf("FILE: %p\n",report_file);
    //printf("SIZE: %d\n",report->report_size);
    //fwrite(report->report,report->report_size, 1,report_file);
    
    //for(int i = 0; i<1216;i++){
    //    if(i == 64)
    //        printf("\n");
    //    printf("%" PRIu8 " ", att_buffer[i]);
    //}
	
	//extract pub key hash
	strncpy(pub_key_hash, att_buffer + 112, 64);

    free(att_buffer);
    //printf("\n");
}

void get_pub_key(uint8_t** key) {
    u64 page_size = sysconf(_SC_PAGESIZE);
    uint8_t* key_buffer = aligned_alloc(page_size, page_size);
	key_buffer[0] = 0;
	//printf("[Client] Allocated 1 page at %p\n", key_buffer);
    struct monitor_call call;
	call.attestation_target = key_buffer;
    u64 ret;
    call.type = get_public_key;
	//printf("[Client] Type: %d\n", call.type);
	//sleep(1);
    ret = ioctl(fd,VMPL_WR,&call);
    //printf("ret = %lld\n", ret);

	// find size of key
	unsigned int key_size = strlen((char*)key_buffer);	
	//printf("[Client] Key size = %d\n", key_size);
	
	// Have space for the terminating null
	(*key) = malloc(key_size + 1);

	strncpy((*key), key_buffer, key_size);
	(*key)[key_size] = 0;

	free(key_buffer);
}

void monitor_init() {
    struct monitor_call call;
    call.type = initMonitor;
    int ret = ioctl(fd,VMPL_WR,&call);
    //printf("Init called\n");

}

void single_exec(){
    struct monitor_call call; 
    uint8_t* att_buffer = aligned_alloc(4096, 4096);
    call.trustlet.size = 1;
    call.trustlet.trustlet_data = att_buffer;
    call.trustlet.zygote = 1;
    call.type = createTrustlet;
      int ret = ioctl(fd,VMPL_WR,&call);
    printf("Init called\n");  
	free(att_buffer);
}

static void _send_policy (uint8_t* encrypted_policy, uint8_t* sender_pub_key) {
    struct monitor_call call;
	call.decryption_context.sender_pub_key = sender_pub_key;
	call.decryption_context.encrypted_data = encrypted_policy;
	call.decryption_context.encrypted_data_size = sizeof(policy) + 16;
    u64 ret;
    call.type = send_policy;
	//printf("[Client] Type: %d\n", call.type);
	//sleep(1);
    ret = ioctl(fd,VMPL_WR,&call);
    //printf("ret = %lld\n", ret);
}

static inline int attestation(policy* p, uint8_t* encrypted_policy, key_pair* keys, uint8_t* public_key) 
{
	uint8_t pub_key_hash[HASH_SIZE];
	uint8_t hash[HASH_SIZE];

	call_attest(pub_key_hash);
	uint8_t* key = NULL;
	get_pub_key(&key);

	if(key == NULL) {
		printf("Could not get key!!\n");
	} else {
		printf("Monitor public key: [");
		for(int i = 0; i < 32; i++) {
			printf("%d ", key[i]);
		}
		printf("]\n");
	}

	my_SHA512(key, strlen(key), hash);

	if(strncmp(pub_key_hash, hash, HASH_SIZE) == 0) {
		printf("The hashes match!!\n");
	} else {
		printf("The hashes don't match :(\n");
	}
	 
	uint8_t nonce[24] = {0};
	int n = encrypt(encrypted_policy, (uint8_t*)p, sizeof(policy), nonce, key, keys->private_key);	
	
	_send_policy(encrypted_policy, public_key);

	free(key);
	return 0;

}

int main(int argc, char** argv)
{
        int32_t value, number;

		key_pair* keys;
		keys = gen_keys();
		printf("Hacl Private key: [");
		for(int i = 0; i < 32; i++) {
			printf("%d ", keys->private_key[i]);
		}
		printf("]\n");
		printf("Hacl public key: [");
		for(int i = 0; i < 32; i++) {
			printf("%d ", keys->public_key[i]);
		}
		printf("]\n");
		// init policy
		policy* p = (policy*)malloc(sizeof(policy)); //TODO: Use malloc?

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
		sleep(1);

        fd = open("/dev/vmpl_device", O_RDWR);
        if(fd < 0) {
                printf("Cannot open device file...\n");
                return -1;
        }
		
		// allocate it outside of attenstaion function to avoid measuring the allocation time 
    	uint8_t* encrypted_policy = aligned_alloc(4096, 4096); 
		if(encrypted_policy == NULL) {
			printf("Can't allocate encrypted_policy\n");
			exit(-1);
		}
		encrypted_policy[0] = 0;
		uint8_t* public_key = aligned_alloc(4096, 4096);
		for(int i = 0; i < 32; i++)
		{
			public_key[i] = keys->public_key[i];
		}
		//float total = 0.0;
		monitor_init();
//		for(int i = 0; i < 1000; i++) {
//			uint64_t start = get_cycles();
			attestation(p, encrypted_policy, keys, public_key);
//			uint64_t end = get_cycles();
//			total += (end - start)/1000;
//		}

//		printf("Attestation time: %f\n", cycles_to_ms(total, get_CPU_freq()));
//		printf("Decryption took %f ms\n", cycles_to_ms(139747880, get_CPU_freq()));

   close_:
        printf("Close");
		free(encrypted_policy);
		free(p);
		free(public_key);
        close(fd);
        return 0;
}
