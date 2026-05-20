# 处理服务端消息
import json


def deal_message(msg):
    data = json.loads(msg)
    return data