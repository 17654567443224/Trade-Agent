import asyncio
import json
import logging
import warnings

from . import WsUtils
from .WebSocketFactory import WebSocketFactory


class WsPrivateAsync:
    def __init__(self, apiKey, passphrase, secretKey, url, useServerTime=None, logger=None, **kwargs):
        self.url = url
        self.subscriptions = set()
        self.callback = None
        self.loop = asyncio.get_event_loop()
        self.factory = WebSocketFactory(url, logger=logger)
        self.apiKey = apiKey
        self.passphrase = passphrase
        self.secretKey = secretKey
        self.useServerTime = False
        self.websocket = None
        self.logger = logger if logger is not None else logging.getLogger(__name__)

        if useServerTime is not None:
            warnings.warn("useServerTime parameter is deprecated. Please remove it.", DeprecationWarning)

    async def connect(self):
        self.websocket = await self.factory.connect()

    async def consume(self):
        async for message in self.websocket:
            if self.callback:
                self.callback(message)

    async def subscribe(self, params: list, callback, id: str = None):
        self.callback = callback
        logRes = await self.login()
        await asyncio.sleep(5)
        if logRes:
            payload_dict = {"op": "subscribe", "args": params}
            if id is not None:
                payload_dict["id"] = id
            await self.websocket.send(json.dumps(payload_dict))

    async def login(self):
        loginPayload = WsUtils.initLoginParams(
            useServerTime=self.useServerTime,
            apiKey=self.apiKey,
            passphrase=self.passphrase,
            secretKey=self.secretKey
        )
        await self.websocket.send(loginPayload)
        return True

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

    async def place_order(self, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        await self.send("order", args, id=id)

    async def batch_orders(self, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        await self.send("batch-orders", args, id=id)

    async def cancel_order(self, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        await self.send("cancel-order", args, id=id)

    async def batch_cancel_orders(self, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        await self.send("batch-cancel-orders", args, id=id)

    async def amend_order(self, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        await self.send("amend-order", args, id=id)

    async def batch_amend_orders(self, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        await self.send("batch-amend-orders", args, id=id)

    async def mass_cancel(self, args: list, callback=None, id: str = None):
        if callback:
            self.callback = callback
        await self.send("mass-cancel", args, id=id)

    async def subscribe_with_login(self, params: list, callback):
        """持续订阅私有频道，内置心跳保活、断线重连与自动重新登录。callback(raw_str)"""
        self.callback = callback
        sub_payload = json.dumps({"op": "subscribe", "args": params})
        while True:
            try:
                self.websocket = await self.factory.connect()
                if self.websocket is None:
                    await asyncio.sleep(5)
                    continue

                # 登录
                login_payload = WsUtils.initLoginParams(
                    useServerTime=self.useServerTime,
                    apiKey=self.apiKey,
                    passphrase=self.passphrase,
                    secretKey=self.secretKey,
                )
                await self.websocket.send(login_payload)
                await asyncio.sleep(1)  # 等待登录确认

                await self.websocket.send(sub_payload)

                while True:
                    try:
                        raw = await asyncio.wait_for(self.websocket.recv(), timeout=25)
                    except asyncio.TimeoutError:
                        # 发心跳
                        try:
                            await self.websocket.send('ping')
                            pong = await asyncio.wait_for(self.websocket.recv(), timeout=5)
                            if isinstance(pong, str) and pong.lower() == 'pong':
                                continue
                            raw = pong
                        except Exception as e:
                            self.logger.error(f'[ws_private] keepalive error: {e}')
                            break
                    except Exception as e:
                        self.logger.error(f'[ws_private] recv error: {e}')
                        break

                    if callback:
                        callback(raw)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.error(f'[ws_private] connection error: {e}')
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
