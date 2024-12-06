#include <linux/module.h>
#include <linux/mm.h>
#include <linux/kdev_t.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/ioctl.h>
#include <linux/err.h>
#include <linux/percpu-defs.h> 
#include <asm/sev.h>

#include <asm/io.h>
#include <linux/mm.h>
#include <asm/tlbflush.h>

#include "vmpl.h"
#include "defs.h"
#include "address_helper.h"

/**
 * rax: call ID
 * rcx: Report storage 
 * 
 * return:
 * 	- 0 on success
 *  - -1 on failure
*/
static long init_monitor(struct monitor_call* mcall){
	struct svsm_call call;
	int res;
	void* ph = pagewalk(mcall->attestation_target);
	call.rcx = (uint64_t)ph;
	call.rax = MONITORCALLID(mcall->type);
	if((res = do_monitor_call(&call)) != 1){
		return -1;
	}
	return 0;
}

/**
 * rax: call ID
 * rcx: Report storage 
 * rdx: Attestation type
 * r8: zygote/trustlet id (if applicable)
 * return:
 * 	- (Size of Report) from rdx on success
 *  - -1 on failure
*/
static long diff_attestation(struct monitor_call* mcall){
  struct svsm_call call;
  void* ph = pagewalk(mcall->monitor_attestation.address);
  call.rcx = (uint64_t)ph; // rcx -> Report storage
  call.rax = MONITORCALLID(mcall->type); // rax -> call ID
  call.rdx = mcall->monitor_attestation.type; // rdx -> attestation type

  switch (mcall->monitor_attestation.type)
  {
    case monitorAttestation:
      /* do nothing */
      break;
    case zygoteAttestation:
      call.r8 = mcall->monitor_attestation.zygote_id;
      break;
    case trustletAttestation:
      call.r8 = mcall->monitor_attestation.trustlet_id;
      break;
    case functionAttestation:
      call.r8 = get_pgd_phys();
      /*
        4k structure that includes hte following:
        1. trustlet_id as a uint64_t
        2. fnInputSize as a uint64_t
        3. fnInput as a void* ptr
        4. fnOutputSize as a uint64_t
        5. fnOutput as a void* ptr
      */
      call.r9 = mcall->monitor_attestation.function_data_ptr;
      break;
    default:
      printk(KERN_ERR "Invalid differential attestation type");
      break;
  }

	int res = do_svsm_protocol(&call);
	if(res != 1)
		return -1;
	return call.rdx;
}

/**
 * rax: call ID
 * rcx: size of Zygote
 * r8:  Zygote Address 
 * 
 * return:
 * 	- ProcessID of Zygote
 *  - -1 on failure
*/
static long create_zygote(struct monitor_call* mcall){
	struct svsm_call call;
	int res;

	call.rax = MONITORCALLID(mcall->type);
	call.rcx = mcall->zygote.size;
	call.r8 = get_pgd_phys();
	call.rdx = mcall->zygote.zygote_data;

	do_monitor_call(&call);

	res = call.rcx;
	return res;
}

/**
 * rax: call ID
 * rcx: ProcessID of Zygote
 * 
 * return:
 * 	-  0 on success
 *  - -1 on failure
*/
static long delete_zygote(struct monitor_call* mcall){
	struct svsm_call call;
	int res;

	call.rax = MONITORCALLID(mcall->type);
	call.rcx = mcall->process_id;

	if((res = do_monitor_call(&call)) != 1)
		return -1;
	return 0;
}

/**
 * rax: call ID
 * rcx: Size of Trustlet data
 * rdx: ProcessID of Zygote
 * r8:  Trustlet data address 
 * 
 * return:
 * 	- ProcessID of Trustlet 
 *  - -1 if failed
*/
static long create_trustlet(struct monitor_call* mcall){
	struct svsm_call call;
	int res;

	call.rax = MONITORCALLID(mcall->type);
	//call.rcx = mcall->trustlet.size;
	//call.r8 = pagewalki(mcall->trustlet.trustlet_data);
	//call.rdx = mcall->trustlet.zygote;
	call.r9 = mcall->trustlet.zygote;

	do_monitor_call(&call);

	return call.rcx;
}

static long invoke_trustlet(struct monitor_call* mcall) {
	struct svsm_call call;
	int res;

	call.rax = MONITORCALLID(mcall->type);
	call.rcx = mcall->process_id;

	do_monitor_call(&call);

	return call.rcx;
}

/**
 * rax: call ID
 * rcx: ProcessID of Trustlet 
 * 
 * return:
 * 	-  0 on success
 *  - -1 on failure
*/
static long delete_trustlet(struct monitor_call* mcall){
	struct svsm_call call;
	int res;

	call.rax = MONITORCALLID(mcall->type);
	call.rcx = mcall->process_id;

	if((res = do_monitor_call(&call))!= 1)
		return -1;
	return 0;
}

static long get_pub_key(struct monitor_call* mcall){

	struct svsm_call call;
	void* ph = pagewalk(mcall->attestation_target);
	call.rcx = (uint64_t)ph;

	call.rax = MONITORCALLID(mcall->type);

	if(do_monitor_call(&call) != 1)
		return -1;
	return 0;
}

static long _send_policy(struct monitor_call* mcall){

	struct svsm_call call;
	void* sender_pub_key_pa = pagewalk(mcall->decryption_context.sender_pub_key);
	void* encrypted_data_pa = pagewalk(mcall->decryption_context.encrypted_data);
	call.r8 = (uint64_t)encrypted_data_pa;
	call.rcx =  (uint64_t)sender_pub_key_pa;
	call.rdx = mcall->decryption_context.encrypted_data_size;
	call.rax = MONITORCALLID(mcall->type);

	if(do_monitor_call(&call) != 1)
		return -1;
	return 0;
}

static long exec_elf(struct monitor_call* mcall) 
{
	struct svsm_call call;
	void* page1_pa = pagewalk(mcall->execute_elf_context.page1);
	printk(KERN_ERR "Elf file page1 PA: %p\n", page1_pa);
	void* page2_pa = pagewalk(mcall->execute_elf_context.page2);
	printk(KERN_ERR "Elf file page2 PA: %p\n", page2_pa);
	call.r8 =  (uint64_t)page1_pa;
	call.rcx =  (uint64_t)page2_pa;
	call.rdx = mcall->execute_elf_context.size;
	call.rax = MONITORCALLID(mcall->type);

	if(do_monitor_call(&call) != 1)
		return -1;
	return 0;
}
/*
 * For now for testing
 * rcx is the size
 * r8 is the physical address of list of pages *
 */


static long load_data(struct monitor_call* mcall){
	printk(KERN_ERR "Working");
	uint64_t size = mcall->data_info.size;
	u8* start_addr = mcall->data_info.start_address;
	struct svsm_call call;
	//uint64_t* pages = get_zeroed_page(GFP_KERNEL);
	//printk(KERN_ERR "SIZE, %d", size);
	/*for(int i = 0; i < size; i++){
		printk(KERN_ERR "Trying address: %x", start_addr + i *4096);
		pages[i] = pagewalk(start_addr + i * 4096);
		printk(KERN_ERR "Physical address: %x", pages[i]);
	}*/

	//Page Table of calling app
	void* pgd_phys = get_pgd_phys();

	printk(KERN_ERR "PGD: %p, %p",get_pgd(),pgd_phys);

	call.rcx = size;
	call.rdx = pgd_phys;
	call.r8 = start_addr;
	//u64 test = pagewalk(start_addr);
	//call.rdx = test;//virt_to_phys(pages);
	//printk(KERN_ERR "ADDRESS: %d", test);//virt_to_phys(pages));
	call.rax = MONITORCALLID(mcall->type);
	printk(KERN_INFO "Size: %d",size);
	do_monitor_call(&call);
	return 0;
}


static long parse_request(struct file *file, unsigned int cmd, unsigned long arg){

	struct monitor_call call;
	void* __user arg_user = (void*)arg;

	if(copy_from_user(&call,arg_user, sizeof(struct monitor_call))){
		printk(KERN_ERR "Copy from user error\n");
		return -1;
	}
	printk(KERN_ERR "Call type: %d\n", call.type);
	printk(KERN_ERR "d: %d\n", create_data_struct);
	switch (call.type)
	{
	
	case initMonitor:
		return init_monitor(&call);
	case attest:
		return diff_attestation(&call);
	case createZygote:
		return create_zygote(&call);
	case createTrustlet:
		return create_trustlet(&call);
	case deleteZygote:
		return delete_zygote(&call);
	case deleteTrustlet:
		return delete_trustlet(&call);
	case get_public_key:
		return get_pub_key(&call);
	case send_policy:
		return _send_policy(&call);
	case execute_elf:
		return exec_elf(&call);
	case create_data_struct:
		return load_data(&call);

	case invokeTrustlet:
		return invoke_trustlet(&call);

	default:
		printk(KERN_ERR "Invalid type");
		break;
	}


	return -1;
}

static long vmpl_ioctl(struct file *file, unsigned int cmd, unsigned long arg){
	printk(KERN_INFO "I: %d\n", cmd);
	switch(cmd){
		case VMPL_WR:
			return parse_request(file,cmd,arg);
		default:
			printk(KERN_INFO "Nothing\n");
	}
	return 0;
}


#include "module.h"
