import datetime
import os
import shutil
import uuid

def parse_directory(directory):

    size = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            size += os.path.getsize(os.path.join(root, file))
    return size

def handler(event):

    key = event.get('object').get('key')
    download_path = '/tmp/{}-{}'.format(key, uuid.uuid4())

    list = [(download_path, event.get('files'))]
    while list:
        current_path, current_level = list.pop()
        os.makedirs(current_path, exist_ok=True)
        for name, contents in current_level.items():
            item_path = os.path.join(current_path, name)
            if isinstance(contents, dict):
                list.append((item_path, contents))
            else:
                with open(item_path, "wb") as f:
                    f.write(contents)

    size = parse_directory(download_path)

    compress_begin = datetime.datetime.now()
    shutil.make_archive(os.path.join(download_path, key), 'zip', root_dir=download_path)
    compress_end = datetime.datetime.now()

    archive_name = '{}.zip'.format(key)
    archive_size = os.path.getsize(os.path.join(download_path, archive_name))
    with open(os.path.join(download_path, archive_name), "rb") as f:
        result = f.read()

    #download_time = (s3_download_stop - s3_download_begin) / datetime.timedelta(microseconds=1)
    #upload_time = (s3_upload_stop - s3_upload_begin) / datetime.timedelta(microseconds=1)
    process_time = (compress_end - compress_begin) / datetime.timedelta(microseconds=1)
    return {
            'result': result,
            'measurement': {
                #'download_time': download_time,
                'download_size': size,
                #'upload_time': upload_time,
                'upload_size': archive_size,
                'compute_time': process_time
            }
        }

