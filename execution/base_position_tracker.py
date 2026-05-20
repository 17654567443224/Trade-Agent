from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
import asyncio


class BasePositionTracker(ABC):
    """所有交易所 PositionTracker 的抽象基类，定义统一接口"""

    def set_position_callback(self, callback: Callable, loop: asyncio.AbstractEventLoop):
        """注册持仓变化回调，子类在 _handle_position 后调用 _fire_callback()"""
        self._position_callback = callback
        self._callback_loop = loop

    def _fire_callback(self):
        """线程安全触发持仓变化回调"""
        cb = getattr(self, '_position_callback', None)
        loop = getattr(self, '_callback_loop', None)
        if cb and loop:
            loop.call_soon_threadsafe(cb)

    @abstractmethod
    async def start(self) -> None:
        """连接 WebSocket，订阅仓位/订单推送"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """断开连接"""
        ...

    @abstractmethod
    def get_positions(self) -> Dict[str, Any]:
        """返回当前仓位快照，key 格式建议：{exchange}:{instId}_{posSide}"""
        ...

    @abstractmethod
    def get_orders(self) -> Dict[str, Any]:
        """返回当前订单快照，key 格式建议：{exchange}:{ordId}"""
        ...
