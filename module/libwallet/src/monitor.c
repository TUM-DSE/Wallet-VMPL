#include "monitor.h"
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>

monitor_connection con;

void monitor_connect() {
    con = open("/dev/vmpl_device", O_RDWR);
    if(con < 0) {
        fprintf(stderr, "Cannot open device file...\n");
        exit(-1);
    }
}

void monitor_close() {
    close(con);
}
