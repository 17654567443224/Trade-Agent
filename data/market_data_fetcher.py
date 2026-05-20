import asyncio
import json
import threading
import time

from SDK.binance.um_futures import UMFutures
from SDK.binance.websocket.um_futures.websocket_client import UMFuturesWebsocketClient
from SDK.okx.extra_url import MARK_KLINE, MARK_PRICE
from SDK.okx.utils import deal_message
from SDK.okx.websocket.WsPublicAsync import WsPublicAsync
from SDK.okx.websocket_manager import EventBus
from utils.logger_engine import LoggerEngine

class Market_Data:
    def __init__(self, source, logger_engine:LoggerEngine):
        """
        source:
                "okx", "binance"
        """
        self.logger = logger_engine.get_logger("data.markdata")
        self.source = source
        self.ebs = EventBus()
        if self.source == "okx":
            import SDK.okx.MarketData as Market
            import SDK.okx.PublicData as Public
            self._okx_mark_price_client: WsPublicAsync = None
            self.my_client: WsPublicAsync = None
            self._mark_price_channels = []
            self.okx_kline_channel = None
            self.publicAPI = Public.PublicAPI(logger=self.logger)
            self.marketAPI = Market.MarketAPI(logger=self.logger)
            self.all_symbols = self.get_okx_all_symbols(instType='SWAP')

        elif self.source == "binance":
            self._id = 0
            self._loop = None
            self._reconnecting = False
            self._mark_price_stopped = True
            self._binance_mark_price_client = None
            self._mark_price_ws_id = None
            self.binance_kline_channel = None
            self._mark_price_symbols: list = []
            self._kline_symbols: list = []
            self._kline_intervals: list = []
            self.kline_wss: dict[int, UMFuturesWebsocketClient] = {}
            self.um_futures_client = UMFutures()

            self.all_symbols = self.get_binance_all_symbols()

    # -----------------okx-----------------------
    def get_kline_from_okx_api(self, symbol, interval, limit=None):
        try:
            res_kl = self.marketAPI.get_mark_price_candlesticks(instId=symbol, limit=limit,
                                                                bar=interval)
            data = deal_message(res_kl)
            return data
        except Exception as e:
            self.logger.error(e)

    def get_okx_all_symbols(self, **kwargs):
        """
                    instType: SWAP,
                    uly: str = '',
                    instId: str = '',
                    instFamily: str = ''
        """
        data = self._get_okx_instruments(**kwargs)
        if not isinstance(data, list):
            self.logger.warning('[okx] get_instruments 返回空或格式异常')
            return []
        symbols_ls = [i.get('instId') for i in data if i.get('state') == 'live']
        return symbols_ls

    def _get_okx_instruments(self, **kwargs):
        try:
            res = self.publicAPI.get_instruments(**kwargs)
            data = deal_message(res)
            return data
        except Exception as e:
            self.logger.error(e)

    def _receive_okx_mark_price(self, _, data):
        if not isinstance(data, dict):
            return
        if data.get('event'):
            return
        items = data.get('data')
        inst_id = data.get('arg', {}).get('instId')
        if not items or not inst_id:
            return
        try:
            price = float(items[0].get('markPx', 0))
            topic = self.source + '_mark_price'
            self.ebs.publish(topic, {inst_id: price})
        except Exception as e:
            self.logger.warning(f'[okx] mark_price publish error: {e}')

    def _receive_okx_kline(self, _, data):
        if not isinstance(data, dict):
            return
        if data.get('event'):
            return
        sym = data.get('arg', {}).get('instId')
        if not sym:
            return
        rows = []
        kline = data.get('data')
        if not kline:
            return
        for item in kline:
            row = self.normalize_kline_row(item)
            if row is not None:
                rows.append(row)
        if not rows:
            return
        if len(rows) == 1:
            rows = rows[0]
        topic = self.source + '_kline'
        self.ebs.publish(topic, {sym: rows})

    async def mark_price_okx_ws_loop(self, symbols: list):
        symbols = self.normalize_okx_symbols(symbols)
        channels = [{'channel': 'mark-price', 'instId': s} for s in symbols]
        self._mark_price_channels = channels
        self._okx_mark_price_client = WsPublicAsync(url=MARK_PRICE, logger=self.logger)
        await self._okx_mark_price_client.subscribe_without_login(channels, self._receive_okx_mark_price)

    async def okx_kline_ws_loop(self, **kwargs):
        """
        symbols: list
        intervals:list
        """
        symbols = self.normalize_symbols(kwargs['symbols'])
        intervals = self.normalize_intervals(kwargs['intervals'])
        channels = self.build_channels(symbols, intervals)
        if not self.okx_kline_channel:
            self.okx_kline_channel = channels
        else:
            self.okx_kline_channel.extend(channels)
        self.my_client = WsPublicAsync(url=MARK_KLINE, logger=self.logger)
        await self.my_client.subscribe_without_login(channels, self._receive_okx_kline)

    def build_channels(self, symbols, intervals):
        channels = []
        if isinstance(intervals, list):
            if len(symbols) != len(intervals):
                if len(intervals) == 1:
                    intervals = intervals * len(symbols)
                else:
                    raise ValueError("symbols ? intervals ?????")
            for s, i in zip(symbols, intervals):
                channels.append({"channel": f"candle{str(i)}", "instId": str(s)})
        return channels

    def normalize_okx_symbols(self, symbols):
        if not isinstance(symbols, list):
            raise ValueError("symbols must be a list")
        normalized = []
        for symbol in symbols:
            value = str(symbol).strip().upper()
            if not value:
                continue
            if value not in normalized:
                normalized.append(value)
        if not normalized:
            raise ValueError("symbols cannot be empty")
        return normalized

    # -----------binance------------
    def get_kline_from_binance_api(self, symbol, interval, limit=None):
        try:
            response = self.um_futures_client.klines(symbol=symbol, interval=getattr(interval, 'value', interval), limit=limit)
            data = self._unwrap_rest_response(response)
            data = self.binance_data_exchange(data)
            return data
        except Exception as e:
            self.logger.error(e)

    def get_binance_all_symbols(self):
        res = self._get_binance_instruments()
        if not isinstance(res, dict):
            self.logger.warning('[binance] exchange_info 返回空或格式异常')
            return []
        res_symbols = res.get('symbols') or []
        symbols_ls = [i.get('symbol') for i in res_symbols if i.get('status') == 'TRADING']
        return symbols_ls

    def _get_binance_instruments(self):
        try:
            res = self._unwrap_rest_response(self.um_futures_client.exchange_info())
            return res
        except Exception as e:
            self.logger.error(e)

    def binance_data_exchange(self, data):
        """rest:[
                  [
                    1499040000000,      // 开盘时间
                    "0.01634790",       // 开盘价
                    "0.80000000",       // 最高价
                    "0.01575800",       // 最低价
                    "0.01577100",       // 收盘价(当前K线未结束的即为最新价)
                    "148976.11427815",  // 成交量
                    1499644799999,      // 收盘时间
                    "2434.19055334",    // 成交额
                    308,                // 成交笔数
                    "1756.87402397",    // 主动买入成交量
                    "28.46694368",      // 主动买入成交额
                    "17928899.62484339" // 请忽略该参数
                  ]
            ]"""
        if isinstance(data, list):
            rows = []
            for k in data:
                row = self.normalize_kline_row(k)
                if row is not None:
                    rows.append(row)
            return rows
        elif isinstance(data, dict):
            # Binance WebSocket 在订阅成功时会返回 {"result": None, "id": xxx}。
            # 这只是确认报文，不是错误事件，需要直接忽略。
            if "result" in data and data.get("result") is None:
                return False
            if data.get("result"):
                return False
            elif data.get("data"):
                if "k" not in data["data"]:
                    return False
                kline = data['data']["k"]
                sym = kline['s']
                row = self.normalize_kline_row([kline['t'], kline['o'], kline['h'], kline['l'], kline['c'], kline['v']])
                if row is None:
                    return False
                return {sym: row}
            else:
                raise ConnectionError(data)
        else:
            return None

    def _unwrap_rest_response(self, response):
        # 有的直接返回 list/dict，有的返回带 .data() 的响应对象。
        if isinstance(response, (list, dict)):
            return response
        if hasattr(response, "data") and callable(response.data):
            return response.data()
        return response

    async def mark_price_ws_loop(self, symbols: list):
        self._mark_price_symbols = self.normalize_symbols(symbols)
        self._mark_price_stopped = False
        client = UMFuturesWebsocketClient(
            on_message=self._receive_mark_price,
            on_close=self._on_mark_price_close,
            on_error=self._on_mark_price_error,
            is_combined=True,
            logger=self.logger,
        )
        mid = self._getId()
        for sym in self._mark_price_symbols:
            client.mark_price(sym, speed=1, id=mid)
        self._binance_mark_price_client = client
        self._mark_price_ws_id = mid
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self._mark_price_stopped = True
            try:
                if self._binance_mark_price_client:
                    self._binance_mark_price_client.stop(self._mark_price_ws_id)
            except Exception as e:
                self.logger.warning(f'[binance] unsubscribe_mark_price error: {e}')

    def normalize_symbols(self, symbols):
        if not isinstance(symbols, list):
            raise ValueError("symbols must be a list")
        normalized = []
        for symbol in symbols:
            value = str(symbol).strip().upper()
            if not value:
                continue
            if value not in normalized:
                normalized.append(value)
        if not normalized:
            raise ValueError("symbols cannot be empty")
        return normalized

    def _on_mark_price_close(self, ws, code, msg):
        if self._mark_price_stopped:
            return
        self.logger.warning(f'[binance] mark_price WS closed, reconnecting...')
        threading.Thread(target=self._reconnect_mark_price, daemon=True).start()

    def _on_mark_price_error(self, ws, error):
        if self._mark_price_stopped:
            return
        self.logger.error(f'[binance] mark_price WS error: {error}')
        threading.Thread(target=self._reconnect_mark_price, daemon=True).start()

    def _on_close(self, ws, close_status_code, close_msg):
        if self._stopped:
            return
        self.logger.warning(f"[binance] WebSocket 关闭 (code={close_status_code}, msg={close_msg})，准备重连...")
        self._schedule_reconnect()

    def _on_error(self, ws, error):
        if self._stopped:
            return
        self.logger.error(f"[binance] WebSocket 错误: {error}，准备重连...")
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnecting:
            return
        self._reconnecting = True
        t = threading.Thread(target=self._reconnect_loop, daemon=True)
        t.start()

    def _reconnect_loop(self):
        while not self._stopped:
            self.logger.info(f"[binance]5秒后尝试重连...")
            time.sleep(5)
            try:
                self._build_ws_client(self._kline_symbols, self._kline_intervals)
                self.logger.info("[binance] 重连成功")
                self._reconnecting = False
                return
            except Exception as e:
                self.logger.error(f"[binance] 重连失败: {e}")

    def _reconnect_mark_price(self):
        while not self._mark_price_stopped:
            time.sleep(5)
            try:
                import asyncio as _asyncio
                _asyncio.run_coroutine_threadsafe(
                    self.subscribe_binance_mark_price(self._mark_price_symbols),  # 基类模板方法
                    self._loop
                )
                return
            except Exception as e:
                self.logger.error(f'[binance] mark_price reconnect failed: {e}')

    async def subscribe_binance_mark_price(self, symbols: list):
        self._mark_price_task = asyncio.create_task(self.mark_price_ws_loop(symbols))

    async def binance_kline_ws_loop(self, **kwargs):
        """
        symbols:list
        intervals:list
        """
        self._loop = asyncio.get_event_loop()
        symbols = self.normalize_symbols(kwargs['symbols'])
        intervals = self.normalize_intervals(kwargs['intervals'])
        self._kline_symbols = symbols
        self._kline_intervals = intervals
        self._stopped = False
        self._build_ws_client(symbols, intervals)
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self._stopped = True
            for i, w in self.kline_wss.items():
                try:
                    w.stop(i)
                except Exception as e:
                    self.logger.error(e)

    def _receive_mark_price(self, _, data):
        data = json.loads(data)
        if not isinstance(data, dict):
            return
        # combined stream: {"data": {"e":"markPriceUpdate","s":"BTCUSDT","p":"..."},...}
        inner = data.get('data') or data
        if not isinstance(inner, dict):
            return
        sym = inner.get('s')
        price = inner.get('p')
        if not sym or price is None:
            return
        try:
            topic = self.source + '_mark_price'
            self.ebs.publish(topic, {sym: float(price)})
        except Exception as e:
            self.logger.warning(f'[binance] mark_price publish error: {e}')

    def stop_receive_kline(self, queue: asyncio.Queue):
        topic = self.source + '_kline'
        self.ebs.unsubscribe(topic, queue)

    def _getId(self):
        self._id += 1
        return self._id

    def _build_ws_client(self, symbols: list, intervals: list):
        client = UMFuturesWebsocketClient(
            on_message=self._receive_binance_kline,
            on_close=self._on_close,
            on_error=self._on_error,
            proxies={
                'host': '127.0.0.1', 'port': '10808'
            },
            is_combined=True,
            logger=self.logger,
        )
        id = self._getId()
        client.kline(symbols, intervals, id)
        self.my_client = client
        self.kline_wss[id] = client

    def _receive_binance_kline(self, _, data):
        data = json.loads(data)
        data = self.binance_data_exchange(data)
        if data is False or data is None:
            return
        topic = self.source + '_kline'
        self.ebs.publish(topic, data)

    def normalize_intervals(self, intervals):
        if not isinstance(intervals, list):
            raise ValueError("intervals must be a list")
        normalized = []
        for interval in intervals:
            value = getattr(interval, "value", interval)
            value = str(value).strip()
            if not value:
                continue
            if value not in normalized:
                normalized.append(value)
        if not normalized:
            raise ValueError("intervals cannot be empty")
        return normalized

    def normalize_kline_row(self, row):
        if row is None:
            return None
        values = list(row[:6])
        if len(values) < 6:
            return None
        try:
            values[0] = int(float(values[0]))
            for idx in range(1, 6):
                values[idx] = float(values[idx])
            return values
        except (TypeError, ValueError):
            self.logger.warning(f"[{self.source}] ignore invalid kline row: {row}")
            return None

async def main():
    lg = LoggerEngine()
    md = Market_Data(source="okx", logger_engine=lg)
    md.ebs.set_loop(asyncio.get_event_loop())
    asyncio.create_task(md.okx_kline_ws_loop(symbols=['BTC-USDT-SWAP', 'ETH-USDT-SWAP'], intervals=['15m', '15m']))
    q:asyncio.Queue = md.ebs.subscribe('okx_kline')

    async def _forward():
        while True:
            data = await q.get()
            print(data)
            q.task_done()
    task = asyncio.create_task(_forward())
    try:
        await asyncio.sleep(60)
    finally:
        task.cancel()
        await task
# if __name__ == '__main__':
#     asyncio.run(main())
#     lg = LoggerEngine()
#     md = Market_Data(source="binance", logger_engine=lg)
#     res = md.get_kline_from_binance_api('BTCUSDT', interval='15m')
#     print(res)
#     #binance {'BTCUSDT': [1776771000000, 76629.0, 76650.0, 76507.9, 76541.8, 500.71]}
#     # okx {'BTC-USDT-SWAP': [[1776771000000, 76641.6, 76662.7, 76514.6, 76569.0, 29354.6]]}