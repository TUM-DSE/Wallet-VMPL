
def handler(event):

    size = len(event['file'])

    #process_time = (process_end - process_begin) / datetime.timedelta(microseconds=1)
    #upload_time = (upload_end - upload_begin) / datetime.timedelta(microseconds=1)
    return {
            'result': event['file'],
            'measurement': {
                'download_time': 0,
                'download_size': 0,
                #'upload_time': upload_time,
                'upload_size': size,
                #'compute_time': process_time
            }
    }
