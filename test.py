import threading
import requests
import time

def getcap():
    url = 'http://127.0.0.1:5000/solve'

    data = {
        "url": "https://www.google.com/recaptcha/api2/demo"
    }

    start = time.time()
    r = requests.post(url, json=data)
    tok = r.json()["token"]
    print(tok)
    print(time.time() - start)
    return tok

tok = getcap()
tok = getcap()
tok = getcap()

input()