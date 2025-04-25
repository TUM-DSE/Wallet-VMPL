import datetime
import os
import sys
import uuid
import pickle
import io

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
    key = data.get('object').get('key')

    download_begin = datetime.datetime.now()
    f_data = client.download_stream(bucket, os.path.join(input_prefix, key))
    download_end = datetime.datetime.now()

    data['data'] = f_data

    data = pickle.dumps(data)

    begin = None
    end = None
    ret = None
    with wallet.Wallet() as w:
        #print(f"trying to execute trustlet {int(os.environ['TRUSTLET'])} with {len(data)} output size.")
        #trustlet = wallet.Trustlet(int(os.environ['TRUSTLET']))
        zygote = wallet.Zygote(ZYGOTE_ID)
        trustlet = zygote.create_trustlet(FUNCTION_CODE)
        output_len = 115343000 # 115342243 -> 115343000 for benchmark 504
                               # 176404566 nur pickle
                               # 115342263 json dann pickle
        trustlet.invoke_trustlet_bin("", 0)
        begin = datetime.datetime.now()
        trustlet.invoke_trustlet_bin(data, 0)
        end = datetime.datetime.now()
        ret = trustlet.invoke_trustlet_bin("", output_len)
        ret = pickle.loads(ret)

    upload_begin = datetime.datetime.now()
    key_name = client.upload_stream(bucket, os.path.join(output_prefix, key), io.BytesIO(ret.get('result').encode()))
    upload_end = datetime.datetime.now()

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

if __name__ == "__main__":
    ZYGOTE_ID = int(sys.argv[2])
    FUNCTION_CODE = sys.argv[3]

    run(host="0.0.0.0", port=int(sys.argv[1]), debug=True)
