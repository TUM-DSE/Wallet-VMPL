import datetime, json, os

def handler(event):
    
    i = int(event["Input"]) * 2
    
    return {"Output": i}



