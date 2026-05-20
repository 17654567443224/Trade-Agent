import asyncio
import json
import logging
import logging.handlers
import queue
import sys
import threading
import os
from typing import Optional


class AutoExcInfoFilter(logging.Filter):
    """
    对 ERROR 及以上级别的日志，若当前处于 except 上下文中，
    自动补全 exc_info，使 formatter 能打印完整 traceback（包含出错的真实位置）。
    等效于将所有 logger.error() 替换成 logger.exception()，无需修改调用代码。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and record.exc_info is None:
            exc = sys.exc_info()
            if exc[0] is not None:
                record.exc_info = exc
        return True


class WsLogHandler(logging.Handler):
    """
    将日志推送到 asyncio 队列，由事件循环转发给所有 WebSocket 客户端。
    在 QueueListener 的后台线程中被调用，通过 call_soon_threadsafe 安全跨线程投递。
    """

    def __init__(self):
        super().__init__()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_clients: set = set()

    def attach(self, loop: asyncio.AbstractEventLoop, ws_clients: set):
        self._loop = loop
        self._ws_clients = ws_clients

    def emit(self, record: logging.LogRecord):
        if not self._loop or not self._ws_clients:
            return
        try:
            msg = json.dumps({
                "type": "log",
                "data": {
                    "time": self.formatter.formatTime(record, self.formatter.datefmt)
                    if self.formatter else record.asctime,
                    "level": record.levelname,
                    "logger": record.name,
                    "file": f"{record.filename}:{record.lineno}",
                    "message": record.getMessage()
                }
            })
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)
        except Exception:
            pass

    async def _broadcast(self, msg: str):
        dead = set()
        for ws in list(self._ws_clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead


class LoggerEngine:

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        log_dir="logs",
        level=logging.INFO,
        max_bytes=50 * 1024 * 1024,
        backup_count=10,
        console=True
    ):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.log_dir = log_dir
        self.level = level

        os.makedirs(log_dir, exist_ok=True)

        self.log_queue = queue.Queue(-1)
        self.queue_handler = logging.handlers.QueueHandler(self.log_queue)
        self.queue_handler.addFilter(AutoExcInfoFilter())

        self.formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        self.file_handler = logging.handlers.RotatingFileHandler(
            filename=os.path.join(log_dir, "app.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        self.file_handler.setFormatter(self.formatter)
        self.file_handler.setLevel(level)

        handlers = [self.file_handler]

        if console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self.formatter)
            console_handler.setLevel(level)
            handlers.append(console_handler)

        # WebSocket 日志 handler（默认不激活，调用 attach_ws 后生效）
        self.ws_handler = WsLogHandler()
        self.ws_handler.setFormatter(self.formatter)
        self.ws_handler.setLevel(level)
        handlers.append(self.ws_handler)

        self.listener = logging.handlers.QueueListener(
            self.log_queue,
            *handlers,
            respect_handler_level=True
        )
        self.listener.start()

    def attach_ws(self, loop: asyncio.AbstractEventLoop, ws_clients: set):
        """绑定事件循环和 ws_clients，日志开始实时推送"""
        self.ws_handler.attach(loop, ws_clients)

    def get_logger(self, name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(self.level)
        if not logger.handlers:
            logger.addHandler(self.queue_handler)
            logger.propagate = False
        return logger

    def shutdown(self):
        self.listener.stop()
