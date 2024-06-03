
LIBMONITOR_PATH = src/monitor_call

LIBMONITOR_SRC = $(wildcard ${LIBMONITOR_PATH}/*.c)
LIBMONITOR_OBJ = $(addsuffix .o,$(LIBMONITOR_SRC:.c=))

LIBPROCESS_PATH = src/process

LIBPROCESS_SRC = $(wildcard ${LIBPROCESS_PATH}/*.c)
LIBPROCESS_OBJ = $(addsuffix .o,$(LIBPROCESS_SRC:.c=))

PROCESS_LIB = src/libtrustedprocess.a
MONITOR_LIB = src/libmonitorcall.a

BIN_PATH = ./bin

CC = gcc
AR = ar

CARGS = -I../module/include -fPIC -shared

${BIN_PATH}/node: ${BIN_PATH} ${MONITOR_LIB} src/main.go 
	go build -gccgoflags '-static -static-libgo' -o ${BIN_PATH}/node src/main.go

${BIN_PATH}: 
	mkdir -p ${BIN_PATH}

%.o: %.c
	${CC} ${CARGS} -c $< -o $@

${MONITOR_LIB}: ${LIBMONITOR_OBJ}
	${AR} rcs ${MONITOR_LIB} ${LIBMONITOR_OBJ} 

${PROCESS_LIB}: ${LIBPROCESS_OBJ}
	${AR} rcs ${PROCESS_LIB} ${LIBPROCESS_OBJ} 


test: ${PROCESS_LIB}
	gcc -o bin/test test/main.c -Lsrc/ -l:libtrustedprocess.a 


clean:
	rm -r ${LIBMONITOR_PATH}/*.o
	rm -r ${BIN_PATH}
	rm ${MONITOR_LIB}