import asyncio
from collections import defaultdict
from typing import Dict, List, Optional


class EventBus:

    def __init__(self, queue_size=10000):
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._queue_size = queue_size
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """绑定 asyncio 事件循环，供跨线程 publish 使用"""
        self._loop = loop

    def subscribe(self, topic: str) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[topic].append(q)
        return q

    def unsubscribe(self, topic: str, queue: asyncio.Queue):
        if topic in self._subscribers:
            self._subscribers[topic].remove(queue)

    def publish(self, topic: str, event):
        if topic not in self._subscribers:
            return
        loop = self._loop
        for q in self._subscribers[topic]:
            def _put(q=q):
                if q.full():
                    q.get_nowait()  # 移除队首（最旧的数据）
                q.put_nowait(event)  # 队尾加入新数据
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_put)
            else:
                _put()
