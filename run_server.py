"""
Trade-Agent unified entry point.

只启动 FastAPI/uvicorn 服务器，工作流由前端"启动工作流"按钮触发。

Usage:
    python run_server.py

Then:
    REST API docs  → http://127.0.0.1:8000/docs
    Frontend dev   → cd frontend && npm run dev  → http://localhost:5173
"""

import asyncio
import sys
import os

# ── make project root importable ─────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
ORCHESTRATION_DIR = os.path.join(ROOT, "orchestration")
for p in [ROOT, ORCHESTRATION_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# workflow 用相对路径 '../config/...' 读取配置，需要把 CWD 切换到 orchestration/
os.chdir(ORCHESTRATION_DIR)

import uvicorn

from api.server import app, get_event_bus, set_workflow
from orchestration.workflow import workflow


async def main() -> None:
    # 1. shared event bus
    event_bus = get_event_bus()

    # 2. 初始化 workflow 对象（仅构造，不启动）
    wf = workflow(source="okx", event_bus=event_bus)
    set_workflow(wf)

    # 3. 只启动 uvicorn；工作流由前端按钮通过 /api/control 启动
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
