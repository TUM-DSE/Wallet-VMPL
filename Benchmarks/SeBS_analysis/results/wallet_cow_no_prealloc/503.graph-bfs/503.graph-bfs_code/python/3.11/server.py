import datetime
import os
import sys
import uuid
import pickle

from bottle import route, run, template, request

import wallet


@route("/alive", method="GET")
def alive():
    return {"result:" "ok"}


@route("/", method="POST")
def process_request():

    data = request.json
    data = pickle.dumps(data)

    begin = None
    end = None
    ret = None
    with wallet.Wallet() as w:
        print(f"trying to execute trustlet {int(os.environ['TRUSTLET'])} with {len(data)} output size.")
        trustlet = wallet.Trustlet(int(os.environ['TRUSTLET']))
        output_len = 53000 # 52542 -> 53000
        trustlet.invoke_trustlet_bin("", 0)
        begin = datetime.datetime.now()
        trustlet.invoke_trustlet_bin(data, 0)
        end = datetime.datetime.now()
        ret = trustlet.invoke_trustlet_bin("", output_len)
        # print(f"ret: {ret}")
        ret = pickle.loads(ret)

    return {
        "begin": begin.strftime("%s.%f"),
        "end": end.strftime("%s.%f"),
        "request_id": str(uuid.uuid4()),
        "is_cold": False,
        "result": {"output": ret},
    }


run(host="0.0.0.0", port=int(sys.argv[1]), debug=True)
