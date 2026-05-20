import asyncio
import json
import logging
from typing import Optional

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

from execution.signal_model import TradeSignal


class SignalPublisher:
    """
    信号发布器：
    - 将交易信号写入内部 asyncio.Queue，供本地消费者消费
    - 可选地通过 aiohttp 将信号异步 POST 到外部 Webhook
    """

    def __init__(self, webhook_url: Optional[str] = None, logger=None):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.webhook_url = webhook_url or ""
        self.logger = logger or logging.getLogger(__name__)

    async def publish(
        self,
        signal: TradeSignal,
        rule_passed: bool,
        sz: float = 0.0,
        order_result: Optional[dict] = None,
    ) -> None:
        """
        发布一条信号。
        - 无论是否通过规则校验均放入队列（携带 rule_passed 标记）
        - sz: 实际下单数量（张数），0 表示未计算或被拒绝
        - order_result: 交易所返回的下单结果，None 表示未实际下单
        - 若配置了 webhook_url 且通过校验，则异步 POST 到外部系统
        """
        payload = {
            "rule_passed": rule_passed,
            "signal": signal.model_dump(),
            "sz": sz,
            "order_result": order_result or {},
        }
        await self._queue.put(payload)

        if rule_passed and order_result:
            success = order_result.get("success", False)
            ord_id = order_result.get("ordId", "")
            self.logger.info(
                f"[signal_publisher] signal published: rule_passed={rule_passed} "
                f"{signal.instId} {signal.action}/{signal.side} sz={sz} "
                f"order={'ok ordId=' + ord_id if success else 'FAILED ' + order_result.get('msg', '')}"
            )
        else:
            self.logger.info(
                f"[signal_publisher] signal published: rule_passed={rule_passed} "
                f"{signal.instId} {signal.action}/{signal.side} size_pct={signal.size_pct}"
            )

        if rule_passed and self.webhook_url:
            await self._post_webhook(payload)

    async def _post_webhook(self, payload: dict) -> None:
        if not _AIOHTTP_AVAILABLE:
            self.logger.warning("[signal_publisher] aiohttp 未安装，跳过 Webhook 推送")
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    self.logger.info(f"[signal_publisher] webhook response: {resp.status}")
        except Exception as e:
            self.logger.error(f"[signal_publisher] webhook POST 失败: {e}")

    async def get(self) -> dict:
        """从队列中取出一条信号，阻塞直到有信号可用"""
        return await self._queue.get()

    def get_nowait(self) -> Optional[dict]:
        """非阻塞取出，队列为空时返回 None"""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    @property
    def qsize(self) -> int:
        return self._queue.qsize()
