all: com_extended run

# ../../module/libwallet/libwallet.a:
# 	$(MAKE) -C ../../module/libwallet/ libwallet.a

com_extended: com.c # compile on host
	gcc -I../../runtime/client/ -o com_extended com.c

run: run.c ../../module/libwallet/libwallet.a # compile in guest
	gcc -I../../module/libwallet/src/ run.c -O3 -g0 -o run -L../../module/libwallet/ -l:libwallet.a
