import hmac
import base64
import datetime
import json

from . import consts as c


def sign(message, secretKey):
    mac = hmac.new(bytes(secretKey, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)


def pre_hash(timestamp, method, request_path, body):
    return str(timestamp) + str.upper(method) + request_path + body


def get_header(api_key, sign, timestamp, passphrase, flag):
    header = dict()
    header[c.CONTENT_TYPE] = c.APPLICATION_JSON
    header[c.OK_ACCESS_KEY] = api_key
    header[c.OK_ACCESS_SIGN] = sign
    header[c.OK_ACCESS_TIMESTAMP] = str(timestamp)
    header[c.OK_ACCESS_PASSPHRASE] = passphrase
    header['x-simulated-trading'] = flag
    return header


def get_header_no_sign(flag):
    header = dict()
    header[c.CONTENT_TYPE] = c.APPLICATION_JSON
    header['x-simulated-trading'] = flag
    return header


def parse_params_to_str(params):
    url = '?'
    for key, value in params.items():
        if value is not None and value != '':
            url = url + str(key) + '=' + str(value) + '&'
    url = url[0:-1]
    return url


def get_timestamp():
    now = datetime.datetime.utcnow()
    t = now.isoformat("T", "milliseconds")
    return t + "Z"


def signature(timestamp, method, request_path, body, secret_key):
    if str(body) == '{}' or str(body) == 'None':
        body = ''
    message = str(timestamp) + str.upper(method) + request_path + str(body)
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)


def deal_message(msg):
    """解析 OKX API 响应，code 非 0 时抛出 ConnectionError，否则返回 data。"""
    j_l = json.loads(json.dumps(msg))
    code = j_l.get('code')
    msg_text = j_l.get('msg')
    if code != "0":
        raise ConnectionError(msg_text)
    return j_l.get('data')
