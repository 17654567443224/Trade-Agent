import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable

from execution.base_position_tracker import BasePositionTracker


class MultiExchangeTracker(BasePositionTracker):
    """
    聚合多个交易所的 PositionTracker，对外暴露与单交易所相同的接口。
    get_positions() / get_orders() 返回所有交易所数据的合并视图，
    key 已由各子 tracker 加上交易所前缀（如 "okx:..." / "binance:..."）以避免冲突。

    支持注册 on_position_update 回调，每次有持仓变化时通过 loop.call_soon_threadsafe 通知。
    """

    def __init__(self, trackers: List[BasePositionTracker], logger=None):
        self._trackers = trackers
        self.logger = logger or logging.getLogger(__name__)
        self._on_position_update: Optional[Callable] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def register_position_callback(self, callback: Callable, loop: asyncio.AbstractEventLoop):
        """注册持仓更新回调，callback 是无参同步函数，会在事件循环线程中调用"""
        self._on_position_update = callback
        self._loop = loop
        for tracker in self._trackers:
            tracker.set_position_callback(self._notify, loop)

    def _notify(self):
        """由子 tracker 在持仓变化时调用，线程安全地 schedule 回调"""
        if self._on_position_update and self._loop:
            self._loop.call_soon_threadsafe(self._on_position_update)

    async def start(self) -> None:
        for tracker in self._trackers:
            try:
                await tracker.start()
            except Exception as e:
                self.logger.error(f"[multi_tracker] {type(tracker).__name__} 启动失败: {e}")

    async def stop(self) -> None:
        for tracker in self._trackers:
            try:
                await tracker.stop()
            except Exception as e:
                self.logger.warning(f"[multi_tracker] {type(tracker).__name__} 停止异常: {e}")

    def get_positions(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for tracker in self._trackers:
            result.update(tracker.get_positions())
        return result

    def get_orders(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for tracker in self._trackers:
            result.update(tracker.get_orders())
        return result
