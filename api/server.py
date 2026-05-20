"""
FastAPI server for Trade-Agent.

Endpoints:
  GET  /api/status
  GET  /api/positions
  GET  /api/orders
  GET  /api/signals?limit=50
  GET  /api/decision
  GET  /api/klines?instId=BTC-USDT-SWAP&exchange=okx
  GET  /api/reflections?limit=10
  POST /api/trigger
  POST /api/control   {"action": "start"|"stop"}
  POST /api/query     {"question": "...", "instId": "BTC-USDT-SWAP"(optional)}
  WS   /ws
"""

import asyncio
import collections
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Deque, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.ws_manager import manager

# ── in-memory ring buffers ────────────────────────────────────────────────────
_MAX_SIGNALS = 200
_MAX_REFLECTIONS = 50

_signal_history: Deque[Dict] = collections.deque(maxlen=_MAX_SIGNALS)
_reflection_history: Deque[Dict] = collections.deque(maxlen=_MAX_REFLECTIONS)

# ── shared state (populated by workflow via event_bus consumer) ───────────────
_state: Dict[str, Any] = {
    "status": "stopped",
    "symbols": [],
    "positions": {},
    "orders": {},
    "latest_decision": None,
    "klines": {},          # {f"{exchange}:{instId}": [candles]}
    "analyst_reports": {   # {"chart": {...}, "fundamental": {...}, "risk": {...}}
        "chart": None,
        "fundamental": None,
        "risk": None,
    },
}

# ── workflow handle (injected by run_server.py) ───────────────────────────────
_workflow_instance: Optional[Any] = None
_workflow_task: Optional[asyncio.Task] = None
_event_bus: asyncio.Queue = asyncio.Queue()

# instId 提取正则：匹配 BTC-USDT-SWAP / BTCUSDT 等常见格式
_INSTID_RE = re.compile(
    r'\b([A-Z]{2,10}[-/]?USDT(?:-SWAP|-PERP)?|'
    r'[A-Z]{2,10}[-/]?BTC(?:-SWAP|-PERP)?|'
    r'[A-Z]{2,10}-[A-Z]{2,6}(?:-SWAP|-PERP)?)\b'
)


def get_event_bus() -> asyncio.Queue:
    return _event_bus


def set_workflow(wf: Any) -> None:
    global _workflow_instance
    _workflow_instance = wf


# ── event bus consumer ────────────────────────────────────────────────────────
async def _consume_events() -> None:
    """Drain the event_bus and forward every event to WebSocket clients."""
    while True:
        try:
            event: Dict = await _event_bus.get()
            etype = event.get("type")
            data = event.get("data", {})

            # update in-memory state
            if etype == "signal":
                _signal_history.append(data)
            elif etype == "state":
                _state["positions"] = data.get("positions", {})
                _state["orders"] = data.get("orders", {})
                _state["symbols"] = data.get("symbols", _state["symbols"])
            elif etype == "analyst":
                role = data.get("role")
                if role:
                    _state["analyst_reports"][role] = data
            elif etype == "decision":
                _state["latest_decision"] = data
            elif etype == "kline":
                key = f"{data.get('exchange', 'unknown')}:{data.get('instId', '')}"
                _state["klines"][key] = data.get("candles", [])
            elif etype == "reflection":
                _reflection_history.append(data)
            elif etype == "system":
                _state["status"] = data.get("status", _state["status"])

            # broadcast to all WS clients
            await manager.broadcast(etype, data)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            import logging
            logging.getLogger("api.server").warning(f"[event_bus] consume error: {exc}")


# ── FastAPI app ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_consume_events())
    yield
    task.cancel()


app = FastAPI(title="Trade-Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    return {
        "status": _state["status"],
        "symbols": _state["symbols"],
        "timestamp": int(time.time()),
    }


@app.get("/api/positions")
async def get_positions():
    return _state["positions"]


@app.get("/api/orders")
async def get_orders():
    return _state["orders"]


@app.get("/api/signals")
async def get_signals(limit: int = 50):
    items = list(_signal_history)
    return items[-limit:]


@app.get("/api/decision")
async def get_decision():
    return _state["latest_decision"] or {}


@app.get("/api/klines")
async def get_klines(instId: str = "BTC-USDT-SWAP", exchange: str = "okx"):
    key = f"{exchange}:{instId}"
    candles = _state["klines"].get(key, [])
    return {"instId": instId, "exchange": exchange, "candles": candles}


@app.get("/api/reflections")
async def get_reflections(limit: int = 10):
    items = list(_reflection_history)
    return items[-limit:]


@app.get("/api/analyst")
async def get_analyst_reports():
    return _state["analyst_reports"]


class ControlRequest(BaseModel):
    action: str  # "start" | "stop"


@app.post("/api/trigger")
async def trigger_analysis():
    """Force an immediate analysis cycle."""
    if _workflow_instance and hasattr(_workflow_instance, "_trigger"):
        _workflow_instance._trigger.set()
        return {"ok": True, "message": "Trigger sent"}
    return {"ok": False, "message": "Workflow not running"}


def _on_workflow_done(task: asyncio.Task) -> None:
    """Task 结束回调：更新状态，记录异常。"""
    import logging
    _state["status"] = "stopped"
    exc = task.exception() if not task.cancelled() else None
    if exc:
        logging.getLogger("api.server").error(f"[workflow] 异常退出: {exc}")
        asyncio.create_task(_event_bus.put(
            {"type": "system", "data": {"status": "error", "message": str(exc)}}
        ))
    else:
        asyncio.create_task(_event_bus.put(
            {"type": "system", "data": {"status": "stopped", "message": "工作流已停止"}}
        ))


@app.post("/api/control")
async def control_workflow(req: ControlRequest):
    global _workflow_task
    if req.action == "start":
        if _workflow_task and not _workflow_task.done():
            return {"ok": False, "message": "工作流已在运行"}
        if _workflow_instance is None:
            return {"ok": False, "message": "工作流未初始化"}
        _workflow_task = asyncio.create_task(_workflow_instance.run())
        _workflow_task.add_done_callback(_on_workflow_done)
        _state["status"] = "running"
        await _event_bus.put({"type": "system", "data": {"status": "running", "message": "工作流已启动"}})
        return {"ok": True, "message": "工作流已启动"}
    elif req.action == "stop":
        if _workflow_task and not _workflow_task.done():
            _workflow_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(_workflow_task), timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            _state["status"] = "stopped"
            await _event_bus.put({"type": "system", "data": {"status": "stopped", "message": "工作流已停止"}})
            return {"ok": True, "message": "工作流已停止"}
        return {"ok": False, "message": "工作流未运行"}
    return {"ok": False, "message": f"未知操作: {req.action}"}


# ── 提问接口 ──────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    instId: Optional[str] = None   # 不传则自动从问题中提取


@app.post("/api/query")
async def run_query(req: QueryRequest):
    """提交临时分析提问，立即返回 query_id；结果通过 WebSocket 流式推送。

    WS 事件序列：
      query_status  → {query_id, status, instId}
      query_analyst → {query_id, role, status, content?}
      query_token   → {query_id, token}          # 综合回答逐 token
      query_done    → {query_id, content}
      query_error   → {query_id, error}
    """
    if _workflow_instance is None:
        return {"ok": False, "message": "工作流未初始化"}

    inst_id = req.instId
    if not inst_id:
        m = _INSTID_RE.search(req.question.upper())
        inst_id = m.group(1) if m else "BTC-USDT-SWAP"

    from orchestration.query_runner import QueryRunner
    runner = QueryRunner(_workflow_instance)
    query_id = uuid.uuid4().hex[:8]
    asyncio.create_task(runner.run(query_id, req.question, inst_id))
    return {"ok": True, "query_id": query_id, "instId": inst_id}


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    # build klines snapshot: reformat {key: candles_list} → {key: KlineData}
    klines_snap: Dict[str, Any] = {}
    for key, candles in _state["klines"].items():
        parts = key.split(":", 1)
        if len(parts) == 2:
            exchange, inst_id = parts
            klines_snap[key] = {"instId": inst_id, "exchange": exchange, "candles": candles}
    # send current snapshot only to the newly connected client
    snapshot = {
        "status": _state["status"],
        "symbols": _state["symbols"],
        "positions": _state["positions"],
        "orders": _state["orders"],
        "latest_decision": _state["latest_decision"],
        "analyst_reports": _state["analyst_reports"],
        "recent_signals": list(_signal_history)[-20:],
        "klines": klines_snap,
    }
    await manager.send_to(ws, "snapshot", snapshot)
    try:
        while True:
            # keep alive — client can send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
