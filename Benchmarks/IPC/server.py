from bottle import route, run, template, request
import ssl
import threading
import requests
import sys

try:
    next_addr = sys.argv[2]
except:
    next_addr = None

try:
    port = int(sys.argv[1])
except:
    port = 4443

@route("/",method="GET")
def do_GET():
    pass
@route("/",method="POST")
def do_POST():
        body = request.body.read()
        #if next_addr:
        #    ret = requests.post(f"http://{next_addr}:4443",data=body)
        #    return_data = ret.content
        #else:
        #    return_data = body
        return_data = body
        return return_data

run(host="0.0.0.0", port=port, debug=False, quite=True)
