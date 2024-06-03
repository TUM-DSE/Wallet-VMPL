#ifndef VMPL_DEFS_H
#define VMPL_DEFS_H

#define PROCESS_MANAGER_SLOT 10
#define MONITORCALLID(x) ((((u64)PROCESS_MANAGER_SLOT)) << 32 | x) 

#define do_monitor_call(x) do_svsm_protocol(x)
extern int do_svsm_protocol(struct svsm_call * call);

#endif