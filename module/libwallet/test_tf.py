import ctypes
lib = ctypes.CDLL("./libwallet.so") 
lib.monitor_connect()
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
zid = lib.create_zygote(b"libpal.so",b"manifest_tf",b"libsysdb.so")
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
func = b"print(\"Hello World!!\")"
tid1 = lib.create_trustlet(zid, func)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_ulonglong)
lib.invoke_trustlet(tid1,b"test data!",0)
#tid2= lib.create_trustlet(zid, func)
#lib.invoke_trustlet(tid2,b"test data!",0)
