import json
import logging
import queue
import threading
import time
from datetime import datetime
from typing import Optional

import mysql.connector
from mysql.connector.connection import MySQLConnection


class OrderStore:
    """
    将终态订单异步持久化到 MySQL。
    使用独立后台线程 + 内存队列，不阻塞事件循环或 WebSocket 回调线程。
    连接断开时自动重连，重连后自动建表。
    """

    _CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS orders (
        id          BIGINT          AUTO_INCREMENT PRIMARY KEY,
        exchange    VARCHAR(20)     NOT NULL,
        ord_id      VARCHAR(64)     NOT NULL,
        inst_id     VARCHAR(64),
        state       VARCHAR(32),
        side        VARCHAR(10),
        pos_side    VARCHAR(20),
        fill_px     DECIMAL(24, 8),
        fill_sz     DECIMAL(24, 8),
        pnl         DECIMAL(24, 8),
        fee         DECIMAL(24, 8),
        order_time  DATETIME,
        raw         JSON,
        UNIQUE KEY  uk_exchange_ordid (exchange, ord_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    _UPSERT = """
    INSERT INTO orders
        (exchange, ord_id, inst_id, state, side, pos_side,
         fill_px, fill_sz, pnl, fee, order_time, raw)
    VALUES
        (%(exchange)s, %(ord_id)s, %(inst_id)s, %(state)s, %(side)s, %(pos_side)s,
         %(fill_px)s, %(fill_sz)s, %(pnl)s, %(fee)s, %(order_time)s, %(raw)s)
    ON DUPLICATE KEY UPDATE
        state      = VALUES(state),
        fill_px    = VALUES(fill_px),
        fill_sz    = VALUES(fill_sz),
        pnl        = VALUES(pnl),
        fee        = VALUES(fee),
        raw        = VALUES(raw);
    """

    def __init__(self, host: str, port: int, user: str, password: str,
                 database: str, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self._config = dict(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            autocommit=True,
        )
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """启动后台写库线程，应在事件循环启动前调用"""
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="order-store-worker"
        )
        self._thread.start()
        self.logger.info("[order_store] 后台写库线程已启动")

    def save(self, exchange: str, order: dict):
        """非阻塞：将终态订单放入队列，由后台线程写入 MySQL"""
        self._queue.put((exchange, order))

    # ------------------------------------------------------------------ #
    #  后台线程
    # ------------------------------------------------------------------ #

    def _worker(self):
        conn: Optional[MySQLConnection] = None
        _fail_count = 0          # 连续失败次数，用于指数退避
        _last_err_msg = ""       # 上次错误信息，相同错误只打一次
        while True:
            exchange, order = self._queue.get()
            try:
                conn = self._ensure_conn(conn)
                row = self._normalize(exchange, order)
                cursor = conn.cursor()
                cursor.execute(self._UPSERT, row)
                cursor.close()
                _fail_count = 0
                _last_err_msg = ""
            except Exception as e:
                err_msg = str(e).split("\n")[0]   # 只取第一行，避免堆栈刷屏
                if err_msg != _last_err_msg:
                    self.logger.error(f"[order_store] 写库失败 ({exchange}): {err_msg}")
                    _last_err_msg = err_msg
                conn = None   # 下次强制重连
                _fail_count += 1
                # 指数退避：1s / 2s / 4s … 最长 60s
                backoff = min(2 ** (_fail_count - 1), 60)
                time.sleep(backoff)
            finally:
                self._queue.task_done()

    def _ensure_conn(self, conn: Optional[MySQLConnection]) -> MySQLConnection:
        if conn:
            try:
                conn.ping(reconnect=False)
                return conn
            except Exception:
                pass
        conn = mysql.connector.connect(**self._config)
        cursor = conn.cursor()
        cursor.execute(self._CREATE_TABLE)
        cursor.close()
        self.logger.info("[order_store] MySQL 连接成功")
        return conn

    # ------------------------------------------------------------------ #
    #  字段归一化
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_float(v) -> Optional[float]:
        try:
            f = float(v)
            return f if f != 0.0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ms_to_dt(ms) -> Optional[datetime]:
        try:
            return datetime.fromtimestamp(int(ms) / 1000)
        except (TypeError, ValueError):
            return None

    def _normalize(self, exchange: str, order: dict) -> dict:
        if exchange == "okx":
            return dict(
                exchange=exchange,
                ord_id=str(order.get("ordId", "")),
                inst_id=order.get("instId", ""),
                state=order.get("state", ""),
                side=order.get("side", ""),
                pos_side=order.get("posSide", ""),
                fill_px=self._to_float(order.get("fillPx")),
                fill_sz=self._to_float(order.get("fillSz")),
                pnl=self._to_float(order.get("pnl")),
                fee=self._to_float(order.get("fee")),
                order_time=self._ms_to_dt(order.get("cTime")),
                raw=json.dumps(order, ensure_ascii=False),
            )
        else:  # binance
            return dict(
                exchange=exchange,
                ord_id=str(order.get("i", "")),
                inst_id=order.get("s", ""),
                state=order.get("X", ""),
                side=order.get("S", ""),
                pos_side=order.get("ps", ""),
                fill_px=self._to_float(order.get("ap")),
                fill_sz=self._to_float(order.get("z")),
                pnl=self._to_float(order.get("rp")),
                fee=self._to_float(order.get("n")),
                order_time=self._ms_to_dt(order.get("T")),
                raw=json.dumps(order, ensure_ascii=False),
            )
