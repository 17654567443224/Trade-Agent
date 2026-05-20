import asyncio
import json
import logging
import threading
from typing import Dict, Any, Optional

from execution.base_position_tracker import BasePositionTracker
from execution.order_store import OrderStore
from SDK.binance.um_futures import UMFutures
from SDK.binance.websocket.um_futures.websocket_client import UMFuturesWebsocketClient

# listen key 续期间隔（秒），Binance 要求每 30 分钟续一次，保守取 25 分钟
_LISTEN_KEY_RENEW_INTERVAL = 25 * 60


class BinancePositionTracker(BasePositionTracker):
    """
    通过 Binance U本位合约 User Data Stream 实时追踪持仓和订单状态。

    流程：
    1. 用 REST 申请 listenKey
    2. 将 listenKey 订阅到 UMFuturesWebsocketClient（同步/线程模型）
    3. 在后台线程接收消息，通过线程安全的方式更新内存数据
    4. 每 25 分钟通过协程续期 listenKey

    key 前缀统一加 "binance:" 便于多交易所合并时区分来源。
    """

    _TERMINAL_STATES = {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}

    def __init__(self, api_key: str, secret_key: str, ws_url: str = "wss://fstream.binance.com",
                 rest_url: str = "https://fapi.binance.com",
                 order_store: Optional[OrderStore] = None,
                 order_memory_limit: int = 200,
                 logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.api_key = api_key
        self.secret_key = secret_key
        self.ws_url = ws_url
        self.rest_url = rest_url

        self._positions: Dict[str, Any] = {}
        self._orders: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._order_store = order_store
        self._order_memory_limit = order_memory_limit

        self._rest_client: Optional[UMFutures] = None
        self._ws_client: Optional[UMFuturesWebsocketClient] = None
        self._listen_key: Optional[str] = None
        self._renew_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    #  WebSocket 消息处理（在 WS 线程中被回调）
    # ------------------------------------------------------------------ #

    def _on_message(self, _, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return

        event_type = msg.get("e")
        if event_type == "ORDER_TRADE_UPDATE":
            self._handle_order(msg.get("o", {}))
        elif event_type == "ACCOUNT_UPDATE":
            for pos in msg.get("a", {}).get("P", []):
                self._handle_position(pos)

    def _handle_order(self, o: dict) -> None:
        ord_id = str(o.get("i", "unknown"))
        key = f"binance:{ord_id}"
        status = o.get("X", "")
        with self._lock:
            if status in self._TERMINAL_STATES:
                if self._order_store:
                    self._order_store.save("binance", o)
                self._orders.pop(key, None)
            else:
                self._orders[key] = o
                while len(self._orders) > self._order_memory_limit:
                    self._orders.pop(next(iter(self._orders)))
        self.logger.info(
            f"[binance_tracker] order updated: {o.get('s')} ordId={ord_id} status={status}"
        )

    def _handle_position(self, pos: dict) -> None:
        symbol = pos.get("s", "unknown")
        pos_side = pos.get("ps", "BOTH")
        key = f"binance:{symbol}_{pos_side}"
        amt = float(pos.get("pa", 0))
        with self._lock:
            if amt == 0.0:
                self._positions.pop(key, None)
            else:
                self._positions[key] = pos
        self.logger.info(f"[binance_tracker] positions updated: {key} pa={amt}")
        self._fire_callback()

    def _on_error(self, _, error) -> None:
        self.logger.error(f"[binance_tracker] ws error: {error}")

    def _on_close(self, _, code, msg) -> None:
        self.logger.warning(f"[binance_tracker] ws closed: code={code} msg={msg}")

    # ------------------------------------------------------------------ #
    #  公共接口
    # ------------------------------------------------------------------ #

    def get_positions(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._positions)

    def get_orders(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._orders)

    async def start(self) -> None:
        loop = asyncio.get_event_loop()

        # 通过 REST 申请 listenKey（同步调用，放到线程池避免阻塞事件循环）
        self._rest_client = UMFutures(key=self.api_key, secret=self.secret_key,
                                      base_url=self.rest_url)
        resp = await loop.run_in_executor(None, self._rest_client.new_listen_key)
        self._listen_key = resp.get("listenKey")
        if not self._listen_key:
            raise RuntimeError(f"[binance_tracker] 申请 listenKey 失败: {resp}")

        # 启动同步 WebSocket 客户端（内部自带线程）
        self._ws_client = UMFuturesWebsocketClient(
            stream_url=self.ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            logger=self.logger,
        )
        self._ws_client.user_data(listen_key=self._listen_key)
        self.logger.info(f"[binance_tracker] 已订阅 user data stream，listenKey={self._listen_key[:8]}…")

        # 启动 listenKey 续期协程
        self._renew_task = asyncio.get_event_loop().create_task(self._renew_loop())

    async def stop(self) -> None:
        if self._renew_task:
            self._renew_task.cancel()
        if self._ws_client:
            self._ws_client.stop()
        if self._rest_client and self._listen_key:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None, lambda: self._rest_client.close_listen_key(self._listen_key)
                )
            except Exception as e:
                self.logger.warning(f"[binance_tracker] 关闭 listenKey 失败: {e}")

    # ------------------------------------------------------------------ #
    #  listenKey 续期
    # ------------------------------------------------------------------ #

    async def _renew_loop(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            await asyncio.sleep(_LISTEN_KEY_RENEW_INTERVAL)
            try:
                await loop.run_in_executor(
                    None, lambda: self._rest_client.renew_listen_key(self._listen_key)
                )
                self.logger.info(f"[binance_tracker] listenKey 续期成功")
            except Exception as e:
                self.logger.error(f"[binance_tracker] listenKey 续期失败: {e}")
