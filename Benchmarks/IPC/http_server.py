from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
from ctypes import *

my_outb_so = CDLL("/root/my_outb.so")


class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    global my_outb_so

    def do_GET(self):
        my_outb_so.my_outb(247)
        print("Got a request")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Hello, world!')


httpd = HTTPServer(('172.45.0.2', 4443), SimpleHTTPRequestHandler)

#httpd.socket = ssl.wrap_socket (httpd.socket, 
#                                keyfile="/root/key.pem", 
#                                certfile='/root/cert.pem', server_side=True)

httpd.serve_forever()


