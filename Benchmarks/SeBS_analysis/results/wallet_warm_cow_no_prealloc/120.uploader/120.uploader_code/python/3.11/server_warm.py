import datetime
import os
import sys
import uuid
import io
import pickle

from function import storage
client = storage.storage.get_instance()

from bottle import route, run, template, request

import wallet

import urllib.request


@route("/alive", method="GET")
def alive():
    return {"result:" "ok"}


@route("/", method="POST")
def process_request():

    data = request.json

    bucket = data.get('bucket').get('bucket')
    output_prefix = data.get('bucket').get('output')
    url = data.get('object').get('url')
    name = os.path.basename(url)
    download_path = '/tmp/{}'.format(name)

    process_begin = datetime.datetime.now()
    urllib.request.urlretrieve(url, filename=download_path)
    process_end = datetime.datetime.now()

    with open(download_path, "rb") as f:
        data['file'] = f.read()

    data = pickle.dumps(data)

    begin = None
    end = None
    ret = None
    with wallet.Wallet() as w:
        #print(f"trying to execute trustlet {int(os.environ['TRUSTLET'])} with {len(data)} output size.")
        #trustlet = wallet.Trustlet(int(os.environ['TRUSTLET']))
        zygote = wallet.Zygote(ZYGOTE_ID)
        trustlet = zygote.create_trustlet(FUNCTION_CODE)
        output_len = 7035000 # 7034961 for benchmark 120
        trustlet.invoke_trustlet_bin("", 0)
        begin = datetime.datetime.now()
        trustlet.invoke_trustlet_bin(data, 0)
        end = datetime.datetime.now()
        ret = trustlet.invoke_trustlet_bin("", output_len)
        ret = pickle.loads(ret)


    upload_begin = datetime.datetime.now()
    key_name = client.upload_stream(bucket, os.path.join(output_prefix, name), io.BytesIO(ret['result']))
    upload_end = datetime.datetime.now()

    ret['result'] = {
        'bucket': bucket,
        'url': url,
        'key': key_name
    }

    return {
        "begin": begin.strftime("%s.%f"),
        "end": (end + (process_end - process_begin) + (upload_end - upload_begin)).strftime("%s.%f"),
        "request_id": str(uuid.uuid4()),
        "is_cold": False,
        "result": {"output": ret},
    }

ZYGOTE_ID = int(sys.argv[2])
FUNCTION_CODE = sys.argv[3]

run(host="0.0.0.0", port=int(sys.argv[1]), debug=True)
