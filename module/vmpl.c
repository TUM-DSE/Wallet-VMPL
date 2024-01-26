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


dev_t dev = 0;
static struct class *dev_class;
static struct cdev cdev;

extern int do_svsm_protocol(struct svsm_call * call);
/*
rax := protocol_number:call_identifier
*/

static void* pagewalk(void* vaddr, struct mm_struct* mm){
	u64 addr = (u64)vaddr;

	pgd_t* pgd = pgd_offset(mm, addr);
	if (pgd_none(*pgd) || pgd_bad(*pgd)) {
		printk( KERN_INFO "Invalid pgd\n");
		return NULL;
	}
	p4d_t* p4d = p4d_offset(pgd,addr);
	if (p4d_none(*p4d) || p4d_bad(*p4d)){
		printk( KERN_INFO "Invalid p4d\n");
		return NULL;
	}
	pud_t *pud = pud_offset(p4d, addr);
	if (pud_none(*pud) || pud_bad(*pud)){
		printk( KERN_INFO "Invalid pud\n");
		return NULL;
	}
	pmd_t *pmd = pmd_offset(pud, addr);
	if (pmd_none(*pmd) || pmd_bad(*pmd)){
		printk( KERN_INFO "Invalid pmd\n");
		return NULL;
	}
	pte_t *pte = pte_offset_kernel(pmd, addr);
	if (pte_none(*pte)) {
		printk( KERN_INFO "Invalid pte\n");
		pte_unmap(pte);
		return NULL;	
	}
	
	struct page *pg = pte_page(*pte);
	pte_unmap(pte);
	return (void*)page_to_phys(pg);

	
}


static int vmpl_open(struct inode *inode, struct file *file){
	printk(KERN_INFO "Device opened\n");
	return 0;
}

static int vmpl_release(struct inode *inode, struct file * file){
	printk(KERN_INFO "Device closed\n");
	return 0;	
}

static long vmpl_request(struct file *file, unsigned int cmd, unsigned long arg){
	return 0;
}

static long vmpl_req(struct file *file, unsigned int cmd, unsigned long arg){
	return 0;
}


static long vmpl_req2(struct file *file, unsigned int cmd, unsigned long arg){
	struct mem memory;
	void* __user arg_user = (void*)arg;

	if(copy_from_user(&memory,arg_user, sizeof(struct mem))){
		printk(KERN_ERR "Copy from user error\n");
		return -1;
	}

	printk(KERN_INFO "Addresses: %llu %llu %llu\n",(u64)memory.pages, (u64)memory.stack, (u64)memory.vmsa);

	void* puserpages = NULL;
	void* puserstack = NULL;
	void* puservmsa = NULL;

	puserpages = pagewalk(memory.pages, current->mm);
	if(puserpages == NULL){
		printk(KERN_ERR "Failed to parse page address 1\n");
		return -1;
	}

	puserstack = pagewalk(memory.stack, current->mm);
	if(puserstack == NULL){
		printk(KERN_ERR "Failed to parse page address 2\n");
		return -1;
	}

	puservmsa = pagewalk(memory.vmsa, current->mm);
	if(puservmsa == NULL){
		printk(KERN_ERR "Failed to parse page address 3\n");
		return -1;
	}

	struct svsm_call call;
	call.rax = (((u64)5) << 32) | 1;
	call.rcx = (u64)puserpages;
	call.rdx = (u64)puserstack;
	call.r8 = (u64)puservmsa;
	
	int res = do_svsm_protocol(&call);
	
	if(res != 0){
		printk(KERN_ERR "Failed to alloc new env\n");
	}
	
	return 0;

}





static long vmpl_ioctl(struct file *file, unsigned int cmd, unsigned long arg){

	switch(cmd){
		case VMPL_WR:
			return vmpl_request(file,cmd,arg);

		case VMPL_W:
			return vmpl_req(file,cmd,arg);

		case VMPL_W2:
			return vmpl_req2(file,cmd,arg);

		default:
			printk(KERN_INFO "Nothing\n");
		

	}

	return 0;
}

static struct file_operations fileops = {
	.owner = THIS_MODULE,
	.open = vmpl_open,
	.release = vmpl_release,
	.unlocked_ioctl = vmpl_ioctl,
};



static int __init vmpl_start(void)
{


	int ret = alloc_chrdev_region(&dev, 0, 1, "vmpls");
	if(ret < 0){
		printk(KERN_ERR "Unable to alloc\n");
		return -1;
	}
	printk(KERN_INFO "%d, %d\n", MAJOR(dev), MINOR(dev));

	cdev_init(&cdev,&fileops);

	ret = cdev_add(&cdev, dev, 1);
	if(ret < 0){
		printk(KERN_ERR "Unable to add device to system\n");
		unregister_chrdev_region(dev,1);
		return -1;
	}

	if(IS_ERR(dev_class = class_create("vmpl_class"))){
		printk(KERN_ERR "Unable to create class struct\n");
		unregister_chrdev_region(dev,1);
		return -1;
	}

	if(IS_ERR(device_create(dev_class,NULL,dev,NULL,"vmpl_device"))){
		printk(KERN_ERR "Unable to create device\n");
		class_destroy(dev_class);
		unregister_chrdev_region(dev,1);
		return -1;
	}




	printk(KERN_INFO "VMPL Driver Initilized\n");

	return 0;
}

static void __exit vmpl_end(void){
        device_destroy(dev_class,dev);
        class_destroy(dev_class);
        cdev_del(&cdev);
        unregister_chrdev_region(dev, 1);
}

module_init(vmpl_start);
module_exit(vmpl_end);
MODULE_LICENSE("GPL");
