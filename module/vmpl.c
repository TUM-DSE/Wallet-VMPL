#include <linux/module.h>
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

#define VMPL_WR _IOWR('a','a',struct svsm_call)


dev_t dev = 0;
static struct class *dev_class;
static struct cdev cdev;
/*
struct svsm_call {
	struct svsm_caa *caa;
	u64 rax;
	u64 rcx;
	u64 rdx;
	u64 r8;
	u64 r9;
};*/

extern int do_svsm_protocol(struct svsm_call * call);
/*
rax := protocol_number:call_identifier
*/


static int vmpl_open(struct inode *inode, struct file *file){
	printk(KERN_INFO "Device opened\n");
	return 0;
}

static int vmpl_release(struct inode *inode, struct file * file){
	printk(KERN_INFO "Device closed\n");
	return 0;	
}

static long vmpl_ioctl(struct file *file, unsigned int cmd, unsigned long arg){
	struct svsm_call user_call;
	void* __user arg_user = (void*)arg;
	printk(KERN_INFO "IOCTL call\n");
	
	switch(cmd){
		case VMPL_WR:
			if(copy_from_user(&user_call,arg_user, sizeof(struct svsm_call))){
				printk(KERN_ERR "Copy from user error\n");
				return -1;
			}
			if(((user_call.rax & 0xffffffff00000000) >>32) != 5){
				printk(KERN_ERR "Invalid Message type\n");
				return -1;
			}
			printk(KERN_INFO "SVMS Protocol Message: \n	rax: %llu\n	rcx: %llu\n	rdx: %llu\n", user_call.rax, user_call.rcx, user_call.rdx);
			int res = do_svsm_protocol(&user_call);
			user_call.rcx = res;
			if(copy_to_user(arg_user, &user_call, sizeof(struct svsm_call))){
				printk(KERN_ERR "Copy to user error\n");
				return -1;
			}
			break;
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
