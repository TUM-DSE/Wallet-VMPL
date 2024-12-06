import ctypes
lib = ctypes.CDLL("./libwallet.so") 
lib.monitor_connect()
lib.create_zygote.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p)
lib.create_zygote(b"libpal.so",b"manifest",b"libsysdb.so")
lib.create_trustlet.argtypes = (ctypes.c_int,ctypes.c_char_p)
func = b"print(\"Hello World\")"
lib.create_trustlet(0, func)
lib.invoke_trustlet.argtypes = (ctypes.c_int, ctypes.c_char_p,)
lib.invoke_trustlet(1,b"")
