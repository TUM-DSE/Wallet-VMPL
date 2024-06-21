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
 * rdx: Query report size
 * 
 * return:
 * 	- (Size of Report) on success
 *  - -1 on failure
*/
static long attest_monitor(struct monitor_call* mcall){
	struct svsm_call call;
	void* ph = pagewalk(mcall->monitor_attestation.address);
	printk(KERN_ERR "Using Page %p for report\n", ph);
	call.rcx = (uint64_t)ph;
	call.rax = (((u64)10) << 32) | 1;
	call.rdx = mcall->monitor_attestation.type;
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
	call.r8 = pagewalki(mcall->zygote.zygote);

	if((res = do_monitor_call(&call)) != 1){
		return -1;
	}
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
	call.rcx = mcall->trustlet.size;
	call.r8 = pagewalki(mcall->trustlet.trustlet_data);
	call.rdx = mcall->trustlet.zygote;

	if((res = do_monitor_call(&call)) != 1)
		return -1;
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
	printk(KERN_ERR "Using Page %p for pub key\n", ph);
	call.rcx = (uint64_t)ph;

	call.rax = MONITORCALLID(mcall->type);

	if(do_monitor_call(&call) != 1)
		return -1;
	return 0;
}



static long parse_request(struct file *file, unsigned int cmd, unsigned long arg){

	struct monitor_call call;
	void* __user arg_user = (void*)arg;

	if(copy_from_user(&call,arg_user, sizeof(struct monitor_call))){
		printk(KERN_ERR "Copy from user error\n");
		return -1;
	}
	printk(KERN_INFO "%d\n", call.type);
	switch (call.type)
	{
	
	case initMonitor:
		return init_monitor(&call);
	case attest:
		return attest_monitor(&call);
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
