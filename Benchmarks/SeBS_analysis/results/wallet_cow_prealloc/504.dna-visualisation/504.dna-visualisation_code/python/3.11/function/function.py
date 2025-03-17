import datetime
import json

# using https://squiggle.readthedocs.io/en/latest/
from squiggle import transform

def handler(event):

    data = event.get('data')

    process_begin = datetime.datetime.now()
    result = transform(data)
    process_end = datetime.datetime.now()

    #download_time = (download_stop - download_begin) / datetime.timedelta(microseconds=1)
    #upload_time = (upload_stop - upload_begin) / datetime.timedelta(microseconds=1)
    process_time = (process_end - process_begin) / datetime.timedelta(microseconds=1)

    return {
            'result': json.dumps(result),
            'measurement': {
                #'download_time': download_time,
                'compute_time': process_time,
                #'upload_time': process_time
            }
    }
