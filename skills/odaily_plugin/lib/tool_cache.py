"""
tool_cache.py
进程内单例缓存，用于检测 tool 返回数据是否发生变化。

用法：
    cache = ToolCache.instance()
    changed = cache.update("tool_name", fingerprint_str)
    # changed=True  → 数据有更新，正常返回
    # changed=False → 数据未变化，在返回内容中追加提示
"""
from __future__ import annotations

import hashlib
import threading


class ToolCache:
    _instance: "ToolCache | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._store: dict[str, str] = {}

    @classmethod
    def instance(cls) -> "ToolCache":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def update(self, key: str, fingerprint: str) -> bool:
        """
        用 fingerprint 更新缓存。
        返回 True 表示数据有变化（或首次调用），False 表示数据未变化。
        """
        h = hashlib.md5(fingerprint.encode("utf-8", errors="replace")).hexdigest()
        with self._lock:
            if self._store.get(key) == h:
                return False
            self._store[key] = h
            return True


NO_UPDATE_HINT = "\n\n⚠️ 【数据无更新】本次数据与上次相同，请直接复用上次的分析结论，无需重新分析。"
