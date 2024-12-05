SRCS:=$(wildcard src/*.c)
OBJS:=${SRCS:c=o}

CFLAGS=-o3 -fpic

ifneq (${NODEBUG},)
CFLAGS+=-DNODEBUG
endif

CFLAGS+=-Iinclude

%.o: %.c
	${CC} ${CFLAGS} -c $< -o $@

libwallet.a: ${SRCS} ${OBJS}
	ar rcs $@ ${OBJS}

libwallet.so: ${SRCS} ${OBJS}
	${CC} -shared ${OBJS} -o $@

clean:
	rm -f ${OBJS}
	rm -f libwallet.*
