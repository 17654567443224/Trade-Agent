import asyncio
import json
import logging

import websockets
from . import WsUtils
from .WebSocketFactory import WebSocketFactory


class WsPublicAsync():
    def __init__(self, url, apiKey='', passphrase='', secretKey='', logger=None, **kwargs):
        self.url = url
        self.subscriptions = set()
        self.callback = None
        self.loop = asyncio.get_event_loop()
        self.factory = WebSocketFactory(url, logger=logger)
        self.websocket = None
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.apiKey = apiKey
        self.passphrase = passphrase
        self.secretKey = secretKey
        self.isLoggedIn = False

    async def connect(self):
        self.websocket = await self.factory.connect()

    async def consume(self):
        async for message in self.websocket:
            if self.callback:
                self.callback(message)

    async def login(self):
        if not self.apiKey or not self.secretKey or not self.passphrase:
            raise ValueError("apiKey, secretKey and passphrase are required for login")
        loginPayload = WsUtils.initLoginParams(
            useServerTime=False,
            apiKey=self.apiKey,
            passphrase=self.passphrase,
            secretKey=self.secretKey
        )
        await self.websocket.send(loginPayload)
        self.isLoggedIn = True
        return True

    async def subscribe(self, params: list, callback, id: str = None):
        self.callback = callback
        payload_dict = {"op": "subscribe", "args": params}
        if id is not None:
            payload_dict["id"] = id
        await self.websocket.send(json.dumps(payload_dict))

    async def unsubscribe(self, params: list, callback, id: str = None):
        self.callback = callback
        payload_dict = {"op": "unsubscribe", "args": params}
        if id is not None:
            payload_dict["id"] = id
        payload = json.dumps(payload_dict)
        self.logger.info(f"unsubscribe: {payload}")
        await self.websocket.send(payload)

    async def send(self, op: str, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        payload_dict = {"op": op, "args": args}
        if id is not None:
            payload_dict["id"] = id
        await self.websocket.send(json.dumps(payload_dict))

    async def subscribe_without_login(self, channels: list, callback):
        """持续订阅公共频道，内置心跳保活与自动重连。callback(None, parsed_dict)"""
        sub_payload = json.dumps({"op": "subscribe", "args": channels})
        while True:
            try:
                self.websocket = await self.factory.connect()
                if self.websocket is None:
                    await asyncio.sleep(5)
                    continue
                await self.websocket.send(sub_payload)
                while True:
                    try:
                        raw = await asyncio.wait_for(self.websocket.recv(), timeout=25)
                    except asyncio.TimeoutError:
                        try:
                            await self.websocket.send('ping')
                            pong = await asyncio.wait_for(self.websocket.recv(), timeout=5)
                            if isinstance(pong, str) and pong.lower() == 'pong':
                                continue
                            raw = pong
                        except Exception as e:
                            self.logger.error(f'[ws] keepalive error: {e}')
                            break
                    except (websockets.exceptions.ConnectionClosed, Exception) as e:
                        self.logger.error(f'[ws] recv error: {e}')
                        break

                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if 'event' in data:
                        continue
                    if data.get('arg') and 'data' in data:
                        callback(None, data)
            except Exception as e:
                self.logger.error(f'[ws] connection error: {e}')
            await asyncio.sleep(3)

    async def stop(self):
        await self.factory.close()

    async def start(self):
        self.logger.info("Connecting to WebSocket...")
        await self.connect()
        self.loop.create_task(self.consume())

    def stop_sync(self):
        if self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.stop(), self.loop)
            future.result(timeout=10)
        else:
            self.loop.run_until_complete(self.stop())
