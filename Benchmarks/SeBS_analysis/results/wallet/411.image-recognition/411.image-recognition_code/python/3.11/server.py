import datetime
import os
import sys
import uuid
import pickle

from function import storage
client = storage.storage.get_instance()

from bottle import route, run, template, request

import wallet


model = None

@route("/alive", method="GET")
def alive():
    return {"result:" "ok"}


@route("/", method="POST")
def process_request():

    data = request.json

    bucket = data.get('bucket').get('bucket')
    input_prefix = data.get('bucket').get('input')
    model_prefix = data.get('bucket').get('model')
    key = data.get('object').get('input')
    model_key = data.get('object').get('model')

    image_download_begin = datetime.datetime.now()
    image = client.download_stream(bucket, os.path.join(input_prefix, key))
    image_download_end = datetime.datetime.now()

    data['image'] = image
    del image

    global model
    print(f"not model: {not model}", flush=True)
    if not model:
        model = True

        model_download_begin = datetime.datetime.now()
        model_b = client.download_stream(bucket, os.path.join(model_prefix, model_key))
        model_download_end = datetime.datetime.now()

        data['model'] = model_b
        del model_b
    else:
        model_download_begin = datetime.datetime.now()
        model_download_end = model_download_begin

    data_pickle = pickle.dumps(data)
    del data

    begin = None
    end = None
    ret = None
    with wallet.Wallet() as w:
        print(f"trying to execute trustlet {int(os.environ['TRUSTLET'])} with {len(data_pickle)} output size.")
        trustlet = wallet.Trustlet(int(os.environ['TRUSTLET']))
        output_len = 200 # 123 -> 200 for benchmark 411
        trustlet.invoke_trustlet("", 0)
        begin = datetime.datetime.now()
        trustlet.invoke_trustlet(data_pickle, 0)
        end = datetime.datetime.now()
        ret = trustlet.invoke_trustlet("", output_len)

        #ret = trustlet.invoke_trustlet_bin(data_pickle, output_len)

        ret = pickle.loads(ret)

    return {
        "begin": begin.strftime("%s.%f"),
        "end": (end + (image_download_end - image_download_begin) + (model_download_end - model_download_begin)).strftime("%s.%f"),
        "request_id": str(uuid.uuid4()),
        "is_cold": False,
        "result": {"output": ret},
    }


run(host="0.0.0.0", port=int(sys.argv[1]), debug=True)
