import datetime
import os
import sys
import uuid
import io
from urllib.parse import unquote_plus
import pickle

from function import storage
client = storage.storage.get_instance()

from bottle import route, run, template, request

import wallet


@route("/alive", method="GET")
def alive():
    return {"result:" "ok"}


@route("/", method="POST")
def process_request():

    data = request.json

    bucket = data.get('bucket').get('bucket')
    input_prefix = data.get('bucket').get('input')
    output_prefix = data.get('bucket').get('output')
    key = unquote_plus(data.get('object').get('key'))

    download_begin = datetime.datetime.now()
    img = client.download_stream(bucket, os.path.join(input_prefix, key))
    download_end = datetime.datetime.now()

    data['img'] = img

    data = pickle.dumps(data)

    begin = None
    end = None
    ret = None
    with wallet.Wallet() as w:
        print(f"trying to execute trustlet {int(os.environ['TRUSTLET'])} with {len(data)} output size.")
        trustlet = wallet.Trustlet(int(os.environ['TRUSTLET']))
        output_len = 11000 # 10480 -> 11000 for benchmark 210
        trustlet.invoke_trustlet_bin("", 0)
        begin = datetime.datetime.now()
        trustlet.invoke_trustlet_bin(data, 0)
        end = datetime.datetime.now()
        ret = trustlet.invoke_trustlet_bin("", output_len)
        ret = pickle.loads(ret)

    upload_begin = datetime.datetime.now()
    key_name = client.upload_stream(bucket, os.path.join(output_prefix, key), ret.get('result'))
    upload_end = datetime.datetime.now()

    file=sys.stderr
    print(f"Input Size: {len(data)} \nOutput Size: {output_len}", file=sys.stderr)

    ret['result'] = {
        'bucket': bucket,
        'key': key_name
    }

    return {
        "begin": begin.strftime("%s.%f"),
        "end": (end + (download_end - download_begin) + (upload_end - upload_begin)).strftime("%s.%f"),
        "request_id": str(uuid.uuid4()),
        "is_cold": False,
        "result": {"output": ret},
    }


run(host="0.0.0.0", port=int(sys.argv[1]), debug=True)
