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
    download_path = '/tmp/{}-{}'.format(key, uuid.uuid4())
    os.makedirs(download_path)

    s3_download_begin = datetime.datetime.now()
    client.download_directory(bucket, os.path.join(input_prefix, key), download_path)
    s3_download_stop = datetime.datetime.now()

    data['files'] = {}
    for dirpath, dirnames, filenames in os.walk(download_path):
        relative_path = os.path.relpath(dirpath, download_path)
        current_level = data['files']

        if relative_path != ".":
            for part in relative_path.split(os.sep):
                current_level = current_level.setdefault(part, {})

        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            with open(file_path, "rb") as f:
                current_level[filename] = f.read()

    data = pickle.dumps(data)

    begin = None
    end = None
    ret = None
    with wallet.Wallet() as w:
        print(f"trying to execute trustlet {int(os.environ['TRUSTLET'])} with {len(data)} output size.")
        trustlet = wallet.Trustlet(int(os.environ['TRUSTLET']))
        output_len = 9328000 # 9327022 -> 9328000 for benchmark 311
        trustlet.invoke_trustlet_bin("", 0)
        begin = datetime.datetime.now()
        trustlet.invoke_trustlet_bin(data, 0)
        end = datetime.datetime.now()
        ret = trustlet.invoke_trustlet_bin("", output_len)
        ret = pickle.loads(ret)

    s3_upload_begin = datetime.datetime.now()
    archive_name = '{}.zip'.format(key)
    key_name = client.upload_stream(bucket, os.path.join(output_prefix, archive_name), io.BytesIO(ret.get('result')))
    s3_upload_stop = datetime.datetime.now()

    ret['result'] = {
        'bucket': bucket,
        'key': key_name
    }

    return {
        "begin": begin.strftime("%s.%f"),
        "end": (end + (s3_download_stop - s3_download_begin) + (s3_upload_stop - s3_upload_begin)).strftime("%s.%f"),
        "request_id": str(uuid.uuid4()),
        "is_cold": False,
        "result": {"output": ret},
    }

if __name__ == "__main__":
    run(host="0.0.0.0", port=int(sys.argv[1]), debug=True)
