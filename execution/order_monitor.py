import asyncio
import logging
import time
from typing import Callable, Awaitable, Optional
from dataclasses import dataclass, field

from execution.signal_model import TradeSignal


@dataclass
class PendingOrder:
    signal: TradeSignal
    ord_id: str
    sz: float
    submitted_at: float = field(default_factory=time.monotonic)
    is_risk_close: bool = False  # True = 风控触发的平仓单


class OrderMonitor:
    """
    后台协程监控挂单状态，超时未成交时取消订单并触发回调：
    - 开仓超时 → on_open_timeout(signal, ord_id, reason) 交给 LLM 重新决策
    - 风控平仓超时 → 立即发市价平仓
    """

    def __init__(
        self,
        order_executor,
        timeout: int = 120,
        check_interval: int = 10,
        on_open_timeout: Optional[Callable[[TradeSignal, str, str], Awaitable[None]]] = None,
        logger=None,
    ):
        self.executor = order_executor
        self.timeout = timeout
        self.check_interval = check_interval
        self.on_open_timeout = on_open_timeout
        self.logger = logger or logging.getLogger(__name__)
        self._pending: dict[str, PendingOrder] = {}  # ord_id -> PendingOrder
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def register(self, signal: TradeSignal, ord_id: str, sz: float, is_risk_close: bool = False):
        """注册一个待监控的挂单"""
        async with self._lock:
            self._pending[ord_id] = PendingOrder(
                signal=signal,
                ord_id=ord_id,
                sz=sz,
                is_risk_close=is_risk_close,
            )
        self.logger.info(f"[order_monitor] 注册监控: {signal.instId} ordId={ord_id} timeout={self.timeout}s")

    async def remove(self, ord_id: str):
        """订单已成交时移除监控"""
        async with self._lock:
            self._pending.pop(ord_id, None)

    async def _loop(self):
        while True:
            await asyncio.sleep(self.check_interval)
            now = time.monotonic()
            async with self._lock:
                timed_out = [
                    o for o in self._pending.values()
                    if now - o.submitted_at >= self.timeout
                ]

            for order in timed_out:
                await self._handle_timeout(order)

    async def _handle_timeout(self, order: PendingOrder):
        signal = order.signal
        reason = f"限价单 {order.ord_id} 超过 {self.timeout}s 未成交"
        self.logger.warning(f"[order_monitor] 超时: {signal.instId} — {reason}")

        # 先取消订单
        cancelled = await self.executor.cancel_order(
            exchange=signal.exchange,
            inst_id=signal.instId,
            ord_id=order.ord_id,
        )
        async with self._lock:
            self._pending.pop(order.ord_id, None)

        if not cancelled:
            self.logger.error(f"[order_monitor] 取消订单失败: {signal.instId} {order.ord_id}，仍触发后续处理")

        if order.is_risk_close:
            # 风控平仓超时 → 立即市价平仓
            self.logger.warning(f"[order_monitor] 风控平仓超时，转市价平仓: {signal.instId}")
            result = await self.executor.close_position_market(
                exchange=signal.exchange,
                inst_id=signal.instId,
                pos_side=signal.posSide,
                sz=order.sz,
            )
            self.logger.info(f"[order_monitor] 市价平仓结果: {result}")
        else:
            # 开仓超时 → 回调给 LLM 重新决策
            if self.on_open_timeout:
                await self.on_open_timeout(signal, order.ord_id, reason)
