#ifndef MONITOR_H_
#define MONITOR_H_

#include <stdbool.h>

typedef int monitor_connection;
extern monitor_connection con;

int monitor_connect();
void monitor_close();

#endif // MONITOR_H_
