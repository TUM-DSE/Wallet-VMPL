
LIBSEV_PATH = deps/sev/target/release
LIBMONITOR_PATH = src/monitor_call

LIBMONITOR_SRC = $(wildcard ${LIBMONITOR_PATH}/*.c)
LIBMONITOR_OBJ = $(addsuffix .o,$(LIBMONITOR_SRC:.c=))

MONITOR_LIB = src/libmonitorcall.a

CC = gcc
AR = ar

CARGS = -I../module/include -fPIC -shared

node: ${MONITOR_LIB} src/main.go
	go build -o node src/main.go

%.o: %.c
	${CC} ${CARGS} -c $< -o $@

${MONITOR_LIB}: ${LIBMONITOR_OBJ}
	${AR} rcs ${MONITOR_LIB} ${LIBMONITOR_OBJ} 

clean:
	rm -r ${LIBMONITOR_PATH}/*.o
	rm ${MONITOR_LIB}