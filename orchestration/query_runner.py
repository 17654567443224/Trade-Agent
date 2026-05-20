"""
QueryRunner: 响应用户临时提问，对指定交易对运行完整三路分析并流式返回结果。

事件序列（通过 event_bus 广播）：
  query_status  → {query_id, status: "started", instId}
  query_analyst → {query_id, role, status: "loading"|"done"|"error", content?}
  query_token   → {query_id, token}          # 逐 token 流式输出
  query_done    → {query_id, content}
  query_error   → {query_id, error}
"""
import asyncio
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

if TYPE_CHECKING:
    from orchestration.workflow import workflow


class QueryRunner:
    def __init__(self, wf: "workflow"):
        self.wf = wf
        self.logger = wf.logger

    # ── helpers ──────────────────────────────────────────────────────────────

    def _put(self, etype: str, data: dict) -> None:
        if self.wf._event_bus is not None:
            try:
                self.wf._event_bus.put_nowait({"type": etype, "data": data})
            except asyncio.QueueFull:
                pass

    # ── public entry ─────────────────────────────────────────────────────────

    async def run(self, query_id: str, question: str, inst_id: str) -> None:
        """完整三路分析 + 流式综合回答。"""
        try:
            self._put("query_status", {"query_id": query_id, "status": "started", "instId": inst_id})

            # 1. 获取 K 线数据（优先用缓存，否则 REST 拉取）
            kline_data = self._fetch_klines(inst_id)

            # 2. 三路分析并行
            for role in ("chart", "fundamental", "risk"):
                self._put("query_analyst", {"query_id": query_id, "role": role, "status": "loading"})

            chart_r, fundamental_r, risk_r = await asyncio.gather(
                self._run_chart(query_id, inst_id, kline_data, question),
                self._run_fundamental(query_id, inst_id, question),
                self._run_risk(query_id, inst_id, question),
                return_exceptions=True,
            )

            # 将异常转为字符串
            chart_r = chart_r if isinstance(chart_r, str) else f"图表分析失败: {chart_r}"
            fundamental_r = fundamental_r if isinstance(fundamental_r, str) else f"基本面分析失败: {fundamental_r}"
            risk_r = risk_r if isinstance(risk_r, str) else f"风险分析失败: {risk_r}"

            # 3. 综合并流式输出
            await self._stream_aggregator(query_id, question, chart_r, fundamental_r, risk_r)

        except Exception as exc:
            self.logger.error(f"[query_runner] 分析异常 {query_id}: {exc}")
            self._put("query_error", {"query_id": query_id, "error": str(exc)})

    # ── private helpers ───────────────────────────────────────────────────────

    def _fetch_klines(self, inst_id: str) -> dict:
        """优先用 WebSocket 缓存，否则调 REST 接口。"""
        cached = self.wf.chart_analyst.kline_data.get(inst_id)
        if cached and len(cached) >= 10:
            data = list(cached)[: self.wf.llm_kline_count + 1]
            self.logger.info(f"[query_runner] 使用缓存 K 线: {inst_id} ({len(data)} 条)")
            return {inst_id: data}

        interval = self.wf.intervals[0] if self.wf.intervals else "15m"
        raw = self.wf.market_fetcher.get_kline_from_okx_api(
            inst_id, interval, limit=self.wf.llm_kline_count
        )
        if raw:
            self.logger.info(f"[query_runner] REST 获取 K 线: {inst_id} ({len(raw)} 条)")
            return {inst_id: raw}

        self.logger.warning(f"[query_runner] 无法获取 {inst_id} K 线，将不含 K 线数据分析")
        return {}

    async def _run_chart(self, query_id: str, inst_id: str, kline_data: dict, question: str) -> str:
        try:
            data_str = str(kline_data) if kline_data else f"{inst_id}（暂无K线数据）"
            messages = [{"role": "user", "content":
                f"用户提问：{question}\n\n请分析以下交易对的K线数据：{data_str}"}]
            resp = await self.wf._invoke_with_fallback(
                self.wf.chart_analyst.create_agent, messages, "chart"
            )
            content = resp["messages"][-1].content if isinstance(resp, dict) else str(resp)
            self._put("query_analyst", {"query_id": query_id, "role": "chart", "status": "done", "content": content})
            return content
        except Exception as exc:
            content = f"图表分析出错: {exc}"
            self._put("query_analyst", {"query_id": query_id, "role": "chart", "status": "error", "content": content})
            return content

    async def _run_fundamental(self, query_id: str, inst_id: str, question: str) -> str:
        try:
            messages = [{"role": "user", "content":
                f"用户提问：{question}\n\n请分析以下交易标的的基本面：{[inst_id]}"}]
            resp = await self.wf._invoke_with_fallback(
                self.wf.fundamental_analyst.create_agent, messages, "fundamental"
            )
            content = resp["messages"][-1].content if isinstance(resp, dict) else str(resp)
            self._put("query_analyst", {"query_id": query_id, "role": "fundamental", "status": "done", "content": content})
            return content
        except Exception as exc:
            content = f"基本面分析出错: {exc}"
            self._put("query_analyst", {"query_id": query_id, "role": "fundamental", "status": "error", "content": content})
            return content

    async def _run_risk(self, query_id: str, inst_id: str, question: str) -> str:
        try:
            positions = self.wf.position_tracker.get_positions()
            messages = [{"role": "user", "content":
                f"用户提问：{question}\n\n交易标的：{inst_id}\n当前持仓：{positions or '无持仓数据'}"}]
            resp = await self.wf._invoke_with_fallback(
                self.wf.risk_analyst.create_agent, messages, "risk"
            )
            content = resp["messages"][-1].content if isinstance(resp, dict) else str(resp)
            self._put("query_analyst", {"query_id": query_id, "role": "risk", "status": "done", "content": content})
            return content
        except Exception as exc:
            content = f"风险分析出错: {exc}"
            self._put("query_analyst", {"query_id": query_id, "role": "risk", "status": "error", "content": content})
            return content

    async def _stream_aggregator(
        self, query_id: str, question: str,
        chart: str, fundamental: str, risk: str,
    ) -> None:
        try:
            rag_ctx = self.wf.reflection_store.query_similar(
                f"{fundamental}\n{chart}\n{risk}"[:2000]
            )
            user_msg = (
                f"用户提问：{question}\n\n"
                f"请综合以下三位分析师的报告，针对用户提问给出投资建议：\n\n"
                f"【图表分析师报告】\n{chart}\n\n"
                f"【基本面分析师报告】\n{fundamental}\n\n"
                f"【风险分析师报告】\n{risk}"
            )
            if rag_ctx:
                user_msg += f"\n\n{rag_ctx}"

            with open('../config/prompts/query_analyst.txt', 'r', encoding='utf-8') as f:
                sys_prompt = f.read()

            lc_msgs = [SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)]
            llm = self.wf.llm_client.aggregator_model

            full = ""
            async for chunk in llm.astream(lc_msgs):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    full += token
                    self._put("query_token", {"query_id": query_id, "token": token})

            self._put("query_done", {"query_id": query_id, "content": full})

        except Exception as exc:
            self.logger.error(f"[query_runner] aggregator 流式失败: {exc}")
            self._put("query_error", {"query_id": query_id, "error": str(exc)})
