#ifndef ADDRESS_HELPER_H
#define ADDRESS_HELPER_H

#include <linux/module.h>
#include <linux/mm.h>
#include <linux/kernel.h>
#include <linux/err.h>

#include <asm/io.h>
#include <linux/mm.h>

static inline void* pagewalk_generic(void* vaddr, struct mm_struct* mm){
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

static void* pagewalk(void* vaddr){
	return pagewalk_generic(vaddr, current->mm);
}

static uint64_t pagewalki(void* vaddr){
	return (uint64_t)pagewalk_generic(vaddr, current->mm);
}


#endif