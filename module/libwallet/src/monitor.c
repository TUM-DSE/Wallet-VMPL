#include "monitor.h"
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>

monitor_connection con;

int monitor_connect() {
    con = open("/dev/vmpl_device", O_RDWR);
    return con;
}

void monitor_close() {
    close(con);
}
