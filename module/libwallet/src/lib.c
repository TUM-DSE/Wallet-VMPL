
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

#include "vmpl.h"
#include "monitor.h"


int stat_get(){
  struct monitor_call call;
  call.type = get_stat;
  uint64_t ret = ioctl(con, VMPL_WR, &call);
  return ret;
}

int stat_reset(){
  struct monitor_call call;
  call.type = reset_stat;
  uint64_t ret = ioctl(con, VMPL_WR, &call);
  return ret;
}
