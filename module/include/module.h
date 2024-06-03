dev_t dev = 0;
static struct class *dev_class;
static struct cdev cdev;


static int vmpl_open(struct inode *inode, struct file *file){
	printk(KERN_INFO "Device opened\n");
	return 0;
}

static int vmpl_release(struct inode *inode, struct file * file){
	printk(KERN_INFO "Device closed\n");
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