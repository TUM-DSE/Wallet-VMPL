import http.client
from ctypes import *

try:
    my_outb_so = CDLL("/root/my_outb.so")
    my_outb_so.my_outb(245)
    connection = http.client.HTTPConnection("172.45.0.2:4443")
    connection.request("GET", "/")
    response = connection.getresponse()
    my_outb_so.my_outb(246)
    print("Status: {} and reason: {}".format(response.status, response.reason))

    connection.close()
except Exception as e:
    print("An exception occured: ", e);

