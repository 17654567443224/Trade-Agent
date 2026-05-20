import asyncio
import json
import logging
from typing import Dict, Any, Optional

from execution.base_position_tracker import BasePositionTracker
from execution.order_store import OrderStore
from SDK.okx.websocket.WsPrivateAsync import WsPrivateAsync


class OkxPositionTracker(BasePositionTracker):
    """
    通过 OKX 私有 WebSocket 实时追踪持仓和订单状态。
    订阅 orders 和 positions 频道，将推送数据更新到内存中。
    key 前缀统一加 "okx:" 便于多交易所合并时区分来源。
    """

    _TERMINAL_STATES = {"filled", "canceled", "mmp_canceled"}

    def __init__(self, api_key: str, passphrase: str, secret_key: str, ws_url: str,
                 order_store: Optional[OrderStore] = None,
                 order_memory_limit: int = 200,
                 logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self._positions: Dict[str, Any] = {}
        self._orders: Dict[str, Any] = {}
        self._order_store = order_store
        self._order_memory_limit = order_memory_limit
        self._ws = WsPrivateAsync(
            apiKey=api_key,
            passphrase=passphrase,
            secretKey=secret_key,
            url=ws_url,
            logger=self.logger,
        )

    def _on_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return

        event = msg.get("event")
        if event in ("login", "subscribe", "error"):
            self.logger.info(f"[okx_tracker] ws event: {msg}")
            return

        arg = msg.get("arg", {})
        channel = arg.get("channel", "")
        data = msg.get("data", [])

        if channel == "orders":
            for item in data:
                self._handle_order(item)
        elif channel == "positions":
            for item in data:
                self._handle_position(item)

    def _handle_order(self, item: dict) -> None:
        ord_id = item.get("ordId", "unknown")
        key = f"okx:{ord_id}"
        state = item.get("state", "")
        if state in self._TERMINAL_STATES:
            if self._order_store:
                self._order_store.save("okx", item)
            self._orders.pop(key, None)
        else:
            self._orders[key] = item
            while len(self._orders) > self._order_memory_limit:
                self._orders.pop(next(iter(self._orders)))
        self.logger.info(f"[okx_tracker] order updated: {item.get('instId')} ordId={ord_id} state={state}")

    def _handle_position(self, item: dict) -> None:
        inst_id = item.get("instId", "unknown")
        pos_side = item.get("posSide", "")
        key = f"okx:{inst_id}_{pos_side}"
        pos = item.get("pos", "0")
        if pos == "0" or pos == 0:
            self._positions.pop(key, None)
        else:
            self._positions[key] = item
        self.logger.info(f"[okx_tracker] positions updated: {key} pos={pos}")
        self._fire_callback()

    def get_positions(self) -> Dict[str, Any]:
        return dict(self._positions)

    def get_orders(self) -> Dict[str, Any]:
        return dict(self._orders)

    async def start(self) -> None:
        params = [
            {"channel": "orders", "instType": "SWAP"},
            {"channel": "positions", "instType": "SWAP"},
        ]
        asyncio.get_event_loop().create_task(
            self._ws.subscribe_with_login(params, callback=self._on_message)
        )
        self.logger.info("[okx_tracker] 已订阅 orders / positions 频道")

    async def stop(self) -> None:
        await self._ws.stop()
