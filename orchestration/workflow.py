from typing import TypedDict, Dict, Any, List, Optional, Annotated
import operator
import asyncio
import time
import yaml
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from analysts.chart_analyst import ChartAnalyst
from analysts.fundamental_analyst import FundamentalAnalyst
from analysts.risk_analyst import RiskAnalyst
from chief_engineer.aggregator import Aggregator
from chief_engineer.compact import LayeredMemory
from chief_engineer.reflection_store import ReflectionStore
from chief_engineer.update_llm import Update_llm
from data.fundamental_fetcher import Fundamental
from data.market_data_fetcher import Market_Data
from execution.signal_model import AggregatorDecision, TradeSignal
from execution.order_store import OrderStore
from execution.signal_publisher import SignalPublisher
from execution.position_tracker import MultiExchangeTracker
from execution.okx_position_tracker import OkxPositionTracker
from execution.binance_position_tracker import BinancePositionTracker
from execution.contract_info import ContractInfoCache
from execution.order_executor import OrderExecutor
from execution.order_monitor import OrderMonitor
from execution.order_sizer import OrderSizer
from execution.rule_guard import RuleGuard
from utils.llm_client import LLMClient
from utils.logger_engine import LoggerEngine
from pydantic import BaseModel, Field
from symbol_select import get_data


class WatchCondition(BaseModel):
    instId: str = Field(description="交易对，如 BTC-USDT-SWAP 或 BTCUSDT")
    direction: str = Field(description="触发方向：above（价格高于阈值触发）或 below（价格低于阈值触发）")
    price: float = Field(description="触发价格阈值")
    reason: str = Field(description="原文条件描述（简短）")


class WatchConditionList(BaseModel):
    conditions: List[WatchCondition] = Field(
        default_factory=list,
        description="从报告中提取的所有价格触发条件，无则返回空列表",
    )


class MistakeCorrection(BaseModel):
    """错误及其纠正"""
    error_description: str = Field(
        description="具体错误的描述",
    )
    cause: str = Field(
        description="错误的根本原因",
    )
    correction_guideline: str = Field(
        description="如何纠正该错误的准则",
    )


class SuccessToKeep(BaseModel):
    """成功经验保留"""
    success_description: str = Field(
        description="成功的策略或操作描述",
    )
    why_it_worked: str = Field(
        description="该策略为何有效",
    )
    preservation_strategy: str = Field(
        description="如何保留和复用该策略",
    )


class TradingReflection(BaseModel):
    """
    交易系统反思与改进报告

    用于记录交易策略的迭代学习：
    - 从错误中提取教训
    - 保留有效策略
    - 防止过拟合
    """
    mistakes_and_corrections: List[MistakeCorrection] = Field(
        description="错误分析列表，从失败中学习的结构化记录",
        min_length=0
    )

    successes_to_keep: List[SuccessToKeep] = Field(
        description="成功经验列表，值得保留和推广的策略",
        min_length=0
    )

    anti_overfitting_notes: str = Field(
        description=(
            "过拟合注意事项，包括："
            "1) 策略对特定市场环境的依赖性"
            "2) 参数优化的边界"
            "3) 保持适应性的方法"
            "4) 避免过度依赖历史数据"
        ),
    )


class Graph_state(TypedDict):
    symbols: list
    timestamp: int

    fundamental: Dict[str, Any]
    chart: Dict[str, Any]
    risk: Dict[str, Any]
    aggregator: Dict[str, Any]

    fundamental_message: Annotated[list, operator.add]
    chart_message: Annotated[list, operator.add]
    risk_message: Annotated[list, operator.add]
    aggregator_message: Annotated[list, operator.add]

    fundamental_update: Optional[TradingReflection]
    chart_update: Optional[TradingReflection]
    risk_update: Optional[TradingReflection]
    aggregator_update: Optional[TradingReflection]

    aggregator_decision: Optional[AggregatorDecision]

    positions: Dict[str, Any]
    orders: Dict[str, Any]
    skip_fundamental: bool


class workflow:
    def __init__(self, source, event_bus: Optional[asyncio.Queue] = None):
        with open('../config/settings.yaml', 'r', encoding='utf-8') as f:
            self.cf = yaml.safe_load(f)
        self._event_bus: Optional[asyncio.Queue] = event_bus
        self.source = source
        self.logger_engine = LoggerEngine()
        self.logger = self.logger_engine.get_logger('orchestration.workflow')
        self.llm_client = LLMClient(self.logger_engine)
        # data
        self.fundamental_fetcher = Fundamental(self.source, self.logger_engine)
        self.market_fetcher = Market_Data(self.source, self.logger_engine)
        # analyst
        self.fundamental_analyst = FundamentalAnalyst(self.llm_client, self.fundamental_fetcher, self.logger_engine, self.source)
        self.chart_analyst = ChartAnalyst(self.llm_client, self.market_fetcher, self.logger_engine, self.source)
        self.risk_analyst = RiskAnalyst(self.llm_client, self.logger_engine, self.source)
        self.aggregator = Aggregator(self.llm_client, self.logger_engine, self.source)
        self.update_llm = Update_llm(self.llm_client, self.logger_engine, self.source)
        # arg
        self.symbols = self.market_fetcher.all_symbols
        self.intervals = self.cf['data']['interval']
        self.llm_kline_count = self.cf['data']['llm_kline_count']
        self.warmup_kline_count = self.cf['data'].get('warmup_kline_count', self.llm_kline_count)
        # 分层记忆（跨轮次持久化）
        self.fundamental_memory = LayeredMemory(self.llm_client.update_model)
        self.chart_memory = LayeredMemory(self.llm_client.update_model)
        self.risk_memory = LayeredMemory(self.llm_client.update_model)
        self.aggregator_memory = LayeredMemory(self.llm_client.update_model)
        self.round_count = 0
        self.compress_every_n = self.cf['data']['compress_every_n']
        self.reflect_every_n = self.cf['data'].get('reflect_every_n', 5)
        self._trade_round_count = 0  # 累计有实际交易的轮次数
        self._graph_running = False
        self._start_time: float = 0.0  # 由 start() 赋值
        self._peak_equity: float = 0.0  # 历史最高总权益，用于回撤熔断
        # RAG：反思知识库（跨进程持久化）
        self.reflection_store = ReflectionStore()
        # execution
        exec_cf = self.cf.get('execution', {})
        db_cf = self.cf.get('database', {})
        self.rule_guard = RuleGuard()
        self.signal_publisher = SignalPublisher(
            webhook_url=exec_cf.get('webhook_url', ''),
            logger=self.logger,
        )
        self.order_store = self._build_order_store(db_cf)
        self._order_memory_limit: int = db_cf.get('order_memory_limit', 200)
        self.position_tracker = self._build_position_tracker(exec_cf)
        self.contract_info = ContractInfoCache(
            okx_flag=exec_cf.get('exchanges', {}).get('okx', {}).get('flag', '0'),
            logger=self.logger,
        )
        self.order_sizer = self._build_order_sizer(exec_cf)
        self.order_executor = self._build_order_executor(exec_cf)
        self.order_monitor = OrderMonitor(
            order_executor=self.order_executor,
            timeout=exec_cf.get('order_timeout', 120),
            on_open_timeout=self._on_open_order_timeout,
            logger=self.logger,
        )
        self._order_max_retries = exec_cf.get('order_max_retries', 3)
        self._drawdown_check_interval = exec_cf.get('drawdown_check_interval', 30)
        # 波动触发紧急分析参数
        data_cf = self.cf.get('data', {})
        self._vol_multiplier: float = data_cf.get('volatility_atr_multiplier', 1.3)
        self._vol_atr_period: int = data_cf.get('volatility_atr_period', 14)
        self._vol_cooldown: float = data_cf.get('volatility_cooldown', 300)
        self._graph: Optional[Any] = None
        self._last_chart_report: str = ""
        self._last_risk_report: str = ""

    def _build_order_store(self, db_cf: dict) -> Optional[OrderStore]:
        mysql_cf = db_cf.get('mysql', {})
        if not mysql_cf.get('host'):
            return None
        try:
            store = OrderStore(
                host=mysql_cf['host'],
                port=mysql_cf.get('port', 3306),
                user=mysql_cf['user'],
                password=mysql_cf['password'],
                database=mysql_cf['database'],
                logger=self.logger,
            )
            return store
        except Exception as e:
            self.logger.warning(f"[order_store] 初始化失败，订单将不持久化: {e}")
            return None

    def _build_position_tracker(self, exec_cf: dict) -> MultiExchangeTracker:
        """根据 config/settings.yaml execution.exchanges 构建多交易所追踪器"""
        trackers = []
        exchanges = exec_cf.get('exchanges', {})

        okx_cf = exchanges.get('okx', {})
        if okx_cf.get('enabled') and okx_cf.get('api_key'):
            trackers.append(OkxPositionTracker(
                api_key=okx_cf['api_key'],
                passphrase=okx_cf.get('passphrase', ''),
                secret_key=okx_cf['secret_key'],
                ws_url=okx_cf.get('ws_url', 'wss://ws.okx.com:8443/ws/v5/private'),
                order_store=self.order_store,
                order_memory_limit=self._order_memory_limit,
                logger=self.logger,
            ))
            self.logger.info("[workflow] OKX PositionTracker 已配置")

        bnb_cf = exchanges.get('binance', {})
        if bnb_cf.get('enabled') and bnb_cf.get('api_key'):
            trackers.append(BinancePositionTracker(
                api_key=bnb_cf['api_key'],
                secret_key=bnb_cf['secret_key'],
                ws_url=bnb_cf.get('ws_url', 'wss://fstream.binance.com'),
                rest_url=bnb_cf.get('rest_url', 'https://fapi.binance.com'),
                order_store=self.order_store,
                order_memory_limit=self._order_memory_limit,
                logger=self.logger,
            ))
            self.logger.info("[workflow] Binance PositionTracker 已配置")

        return MultiExchangeTracker(trackers, logger=self.logger)

    def _build_order_sizer(self, exec_cf: dict) -> OrderSizer:
        exchanges = exec_cf.get('exchanges', {})
        okx_cf = exchanges.get('okx', {})
        bnb_cf = exchanges.get('binance', {})
        return OrderSizer(
            contract_info=self.contract_info,
            okx_api_key=okx_cf.get('api_key', ''),
            okx_passphrase=okx_cf.get('passphrase', ''),
            okx_secret_key=okx_cf.get('secret_key', ''),
            okx_flag=okx_cf.get('flag', '0'),
            binance_api_key=bnb_cf.get('api_key', ''),
            binance_secret_key=bnb_cf.get('secret_key', ''),
            binance_rest_url=bnb_cf.get('rest_url', 'https://fapi.binance.com'),
            logger=self.logger,
        )

    def _build_order_executor(self, exec_cf: dict) -> OrderExecutor:
        exchanges = exec_cf.get('exchanges', {})
        okx_cf = exchanges.get('okx', {})
        bnb_cf = exchanges.get('binance', {})
        return OrderExecutor(
            okx_api_key=okx_cf.get('api_key', ''),
            okx_secret_key=okx_cf.get('secret_key', ''),
            okx_passphrase=okx_cf.get('passphrase', ''),
            okx_flag=okx_cf.get('flag', '0'),
            okx_td_mode=okx_cf.get('td_mode', 'cross'),
            binance_api_key=bnb_cf.get('api_key', ''),
            binance_secret_key=bnb_cf.get('secret_key', ''),
            binance_rest_url=bnb_cf.get('rest_url', 'https://fapi.binance.com'),
            binance_hedge_mode=bnb_cf.get('hedge_mode', True),
            logger=self.logger,
        )

    def _put_event(self, event_type: str, data: Any) -> None:
        """Put an event onto the event_bus (fire-and-forget, non-blocking)."""
        if self._event_bus is not None:
            try:
                self._event_bus.put_nowait({"type": event_type, "data": data})
            except asyncio.QueueFull:
                pass

    async def start(self):
        """启动 WebSocket 数据订阅，在 workflow 运行前调用"""
        self._start_time = time.monotonic()
        if self.order_store:
            self.order_store.start()
        self.market_fetcher.ebs.set_loop(asyncio.get_event_loop())
        await self.chart_analyst.gather_data(symbols=self.symbols, interval=self.intervals)
        self.chart_analyst.set_volatility_callback(
            self._on_volatility,
            cooldown=self._vol_cooldown,
            multiplier=self._vol_multiplier,
            atr_period=self._vol_atr_period,
        )
        self.chart_analyst.set_price_alert_callback(self._on_price_alert)
        self.chart_analyst.set_kline_bar_callback(self._on_kline_bar)
        # 工作流启动后立即把交易对列表推给前端，无需等待第一轮分析完成
        self._put_event("state", {
            "symbols": list(self.symbols),
            "positions": {},
            "orders": {},
        })

        # 加载合约面值缓存
        exchanges = self.cf.get('execution', {}).get('exchanges', {})
        await self.contract_info.load(
            load_okx=exchanges.get('okx', {}).get('enabled', False),
            load_binance=exchanges.get('binance', {}).get('enabled', False),
        )

        if self.position_tracker._trackers:
            try:
                await self.position_tracker.start()
                self.position_tracker.register_position_callback(
                    self._on_position_update,
                    asyncio.get_event_loop(),
                )
            except Exception as e:
                self.logger.warning(f"[position_tracker] 启动失败（将使用空仓位）: {e}")

    async def _invoke_with_fallback(self, create_agent_fn, messages: list, role: str) -> dict:
        """
        调用 agent，失败时自动切换下一个模型重试。
        create_agent_fn: 无参函数，返回新 agent（每次切换后重新调用）
        role: llm_client.switch_model 的角色名，如 'fundamental'/'chart'/'risk'/'aggregator'
        """
        last_exc = None
        # 模型列表长度即重试上限；switch_model 到头后会重置回第一个
        supplier = next(iter(vars(self.llm_client).get(role, {}) or {}), None)
        model_count = len(
            (getattr(self.llm_client, role, {}) or {}).get(supplier, {}).get('model_id', [1])
        ) if supplier else 1
        max_retries = max(model_count, 1)

        for attempt in range(max_retries):
            agent = create_agent_fn()
            try:
                return await agent.ainvoke({"messages": messages})
            except Exception as e:
                last_exc = e
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"[{role}] 第 {attempt + 1} 次调用失败，切换备用模型: {e}"
                    )
                    self.llm_client.switch_model(role)
        raise last_exc

    async def _fundamental_node(self, state: Graph_state):
        if state.get('skip_fundamental'):
            self.logger.info("[fundamental] 跳过基本面分析（波动触发的紧急分析）")
            return {}
        symbols = state.get('symbols')
        if not symbols:
            raise ValueError("找不到交易对")

        # fd_data = self.fundamental_analyst.gather_data(symbols)
        # if not fd_data:
        #     self.logger.error("fd数据获取失败")
        #     return {}

        messages = list(state.get('fundamental_message') or [])
        context = self.fundamental_memory.get_context_for_llm()
        user_prompt = (
            f"【历史上下文】\n{context}\n\n" if context else ""
        ) + f"分析基本面数据,交易标的如下:{symbols}"
        messages.append({"role": "user", "content": user_prompt})

        response = await self._invoke_with_fallback(
            self.fundamental_analyst.create_agent, messages, "fundamental"
        )

        content = response["messages"][-1].content if isinstance(response, dict) else str(response)
        messages.append({"role": "assistant", "content": content})

        self._put_event("analyst", {"role": "fundamental", "content": content, "timestamp": int(time.time())})
        return {"fundamental_message": messages}

    async def _chart_node(self, state: Graph_state):
        symbols = state.get('symbols')
        if not symbols:
            raise ValueError("找不到交易对")

        # 预热检查：所有 symbol 的 K 线数量都必须达到 warmup_kline_count
        kline_counts = {
            sym: len(self.chart_analyst.kline_data[sym])
            for sym in symbols
            if sym in self.chart_analyst.kline_data
        }

        # 超时阈值：启动后超过一个 run_interval 仍然完全没数据，视为不支持该品种
        elapsed = time.monotonic() - self._start_time
        run_interval = self.cf['data'].get('run_interval', 900)
        if elapsed > run_interval:
            dead = [
                sym for sym in symbols
                if kline_counts.get(sym, 0) == 0
            ]
            if dead:
                self.logger.warning(
                    f"[chart] 以下品种启动后超过 {run_interval}s 仍无K线数据，自动剔除: {dead}"
                )
                self.symbols = [s for s in self.symbols if s not in dead]
                symbols = self.symbols

        not_ready = [
            sym for sym in symbols
            if kline_counts.get(sym, 0) < self.warmup_kline_count
        ]
        if not_ready:
            progress = ", ".join(
                f"{sym}={kline_counts.get(sym, 0)}/{self.warmup_kline_count}"
                for sym in not_ready
            )
            self.logger.info(f"[chart] K线预热中，跳过本轮分析（{progress}）")
            return {}

        data = {k: list(self.chart_analyst.kline_data[k])[0:self.llm_kline_count + 1]
                for k in symbols if k in self.chart_analyst.kline_data}
        data = get_data(data)
        if not data:
            self.logger.info("暂无kline数据")
            return {}

        messages = list(state.get('chart_message') or [])
        context = self.chart_memory.get_context_for_llm()
        user_prompt = (
            f"【历史上下文】\n{context}\n\n" if context else ""
        ) + f"分析以下交易对的k线数据：{data}"
        messages.append({"role": "user", "content": user_prompt})

        response = await self._invoke_with_fallback(
            self.chart_analyst.create_agent, messages, "chart"
        )

        content = response["messages"][-1].content if isinstance(response, dict) else str(response)
        messages.append({"role": "assistant", "content": content})
        self._last_chart_report = content

        self._put_event("analyst", {"role": "chart", "content": content, "timestamp": int(time.time())})
        # 把原始 K 线数组转换成前端 lightweight-charts 需要的格式
        # 原始格式: [ts_ms, open, high, low, close, vol, ...]
        for sym, candles in data.items():
            exchange = self.source
            formatted = []
            for bar in candles:
                try:
                    formatted.append({
                        "time": int(bar[0]) // 1000,   # 毫秒 → 秒
                        "open":  float(bar[1]),
                        "high":  float(bar[2]),
                        "low":   float(bar[3]),
                        "close": float(bar[4]),
                        "volume": float(bar[5]) if len(bar) > 5 else 0,
                    })
                except (IndexError, ValueError, TypeError):
                    continue
            formatted.sort(key=lambda x: x["time"])
            self._put_event("kline", {"instId": sym, "exchange": exchange, "candles": formatted})
        return {"chart_message": messages}

    async def _risk_node(self, state: Graph_state):
        symbols = state.get('symbols')
        if not symbols:
            raise ValueError("找不到交易对")

        data = {k: self.risk_analyst.positions[k] for k in symbols if k in self.risk_analyst.positions}
        if not data:
            self.logger.info("暂无positions数据")
            return {}

        messages = list(state.get('risk_message') or [])
        context = self.risk_memory.get_context_for_llm()
        user_prompt = (
            f"【历史上下文】\n{context}\n\n" if context else ""
        ) + f"分析positions数据，数据如下：{data}"
        messages.append({"role": "user", "content": user_prompt})

        response = await self._invoke_with_fallback(
            self.risk_analyst.create_agent, messages, "risk"
        )

        content = response["messages"][-1].content if isinstance(response, dict) else str(response)
        messages.append({"role": "assistant", "content": content})
        self._last_risk_report = content

        self._put_event("analyst", {"role": "risk", "content": content, "timestamp": int(time.time())})
        return {"risk_message": messages}

    async def _aggregator_node(self, state: Graph_state):
        symbols = state.get('symbols')
        if not symbols:
            raise ValueError("找不到交易对")

        def get_last_content(messages):
            if not messages:
                return "无数据"
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "无数据")
                elif hasattr(msg, 'content'):
                    return msg.content
            return "无数据"

        fd_report = get_last_content(state.get('fundamental_message') or [])
        chart_report = get_last_content(state.get('chart_message') or [])
        risk_report = get_last_content(state.get('risk_message') or [])

        messages = list(state.get('aggregator_message') or [])

        # RAG：用三份报告作为 query，检索历史相似反思经验
        rag_query = f"{fd_report}\n{chart_report}\n{risk_report}"[:2000]
        rag_context = self.reflection_store.query_similar(rag_query)

        user_prompt = (
            f"请综合以下三位分析师的报告，给出最终交易决策：\n\n"
            f"【基本面分析师报告】\n{fd_report}\n\n"
            f"【图表分析师报告】\n{chart_report}\n\n"
            f"【风险分析师报告】\n{risk_report}"
        )
        if rag_context:
            user_prompt += f"\n\n{rag_context}"
        messages.append({"role": "user", "content": user_prompt})

        agent = self.aggregator.create_agent()
        response = await agent.ainvoke({"messages": messages})

        content = response["messages"][-1].content if isinstance(response, dict) else str(response)
        messages.append({"role": "assistant", "content": content})

        # 额外调用 structured_output 提取结构化决策
        aggregator_decision = None
        try:
            structured_llm = self.llm_client.aggregator_model.with_structured_output(AggregatorDecision)
            aggregator_decision = structured_llm.invoke([
                {"role": "user", "content": (
                    user_prompt
                    + f"\n\n以上分析师报告对应的最终综合决策内容如下：\n{content}\n\n"
                    "请以 JSON 格式输出结构化决策，必须包含以下英文字段：\n"
                    "- signals: 交易信号列表，每项必须包含：\n"
                    f"  - exchange: 交易所名称，固定填 {self.source}\n"
                    "  - instId: 交易对，如 BTC-USDT-SWAP\n"
                    "  - action: open（开仓）/ close（平仓）/ hold（观望）\n"
                    "  - side: buy / sell\n"
                    "  - posSide: long / short\n"
                    "  - size_pct: 仓位占比 0.0~1.0\n"
                    "  - leverage: 杠杆倍数（整数，最小1）\n"
                    "  - order_type: market / limit\n"
                    "  - px: 限价单价格字符串，市价单填 null\n"
                    "  - sl_px: 止损价格字符串，必填\n"
                    "  - tp_px: 止盈价格字符串，可为 null\n"
                    "  - reason: 决策依据说明\n"
                    "- market_summary: 市场综合摘要（字符串）\n"
                    "- confidence: 决策置信度 0.0~1.0（浮点数）"
                )}
            ])
        except Exception as e:
            self.logger.error(f"[aggregator] structured_output 失败: {e}")

        if aggregator_decision:
            self._put_event("decision", {
                "market_summary": aggregator_decision.market_summary,
                "confidence": aggregator_decision.confidence,
                "signals": [s.model_dump() for s in aggregator_decision.signals],
            })
        return {"aggregator_message": messages, "aggregator_decision": aggregator_decision}

    async def _execute_node(self, state: Graph_state):
        """校验并发布交易信号，同步最新仓位/订单到 state"""
        decision: Optional[AggregatorDecision] = state.get('aggregator_decision')
        if not decision:
            self.logger.info("[execute] 无结构化决策，跳过执行节点")
            return {}

        current_positions = self.position_tracker.get_positions()
        current_orders = self.position_tracker.get_orders()

        for signal in decision.signals:
            if signal.action == "hold":
                self.logger.info(f"[execute] hold 信号，跳过: {signal.instId}")
                continue

            # 以 source 为准强制覆盖 LLM 填写的 exchange，避免 LLM 填错
            if signal.exchange != self.source:
                self.logger.info(f"[execute] exchange 覆盖: {signal.exchange} → {self.source}")
                signal = signal.model_copy(update={"exchange": self.source})

            if signal.action == "open":
                passed, reason = self.rule_guard.check_position_count(current_positions)
                if not passed:
                    self.logger.warning(f"[execute] 信号被拒（持仓数量）: {signal.instId} — {reason}")
                    await self.signal_publisher.publish(signal, rule_passed=False)
                    continue

                passed, reason = self.rule_guard.check_position_size(signal.size_pct)
                if not passed:
                    self.logger.warning(f"[execute] 信号被拒（仓位比例）: {signal.instId} — {reason}")
                    await self.signal_publisher.publish(signal, rule_passed=False)
                    continue

                # 杠杆超限时截断到最大值，不拒绝信号
                passed, reason = self.rule_guard.check_leverage(signal.leverage)
                if not passed:
                    self.logger.warning(f"[execute] 杠杆截断: {signal.instId} — {reason}")
                    signal = signal.model_copy(update={"leverage": self.rule_guard.max_leverage})

            # 止损价格杠杆校验：入场价用 px（限价单）或 tick_data（市价单）
            entry_px = None
            if signal.px:
                try:
                    entry_px = float(signal.px)
                except ValueError:
                    pass
            if entry_px is None:
                tick = self.chart_analyst.tick_data.get(signal.instId)
                if tick:
                    try:
                        entry_px = float(tick)
                    except (ValueError, TypeError):
                        pass
            if entry_px and signal.posSide:
                if signal.sl_px:
                    valid, reason, corrected_sl = self.rule_guard.check_sl_px(
                        sl_px=signal.sl_px,
                        entry_px=entry_px,
                        pos_side=signal.posSide,
                        leverage=signal.leverage,
                    )
                    if not valid:
                        self.logger.warning(f"[execute] 止损修正: {signal.instId} — {reason}")
                        signal = signal.model_copy(update={"sl_px": corrected_sl})

                if signal.tp_px:
                    valid, reason, corrected_tp = self.rule_guard.check_tp_px(
                        tp_px=signal.tp_px,
                        entry_px=entry_px,
                        pos_side=signal.posSide,
                    )
                    if not valid:
                        self.logger.warning(f"[execute] 止盈移除: {signal.instId} — {reason}")
                        signal = signal.model_copy(update={"tp_px": corrected_tp})

            # 计算实际下单数量
            mark_px = float(signal.px) if signal.px else None
            try:
                sz = await self.order_sizer.compute(
                    exchange=signal.exchange,
                    inst_id=signal.instId,
                    size_pct=signal.size_pct,
                    mark_px=mark_px,
                )
            except Exception as e:
                self.logger.error(f"[execute] 数量计算失败 {signal.instId}: {e}，使用 sz=1")
                sz = 1.0

            # 实际下单（仅在对应交易所已配置 API Key 时执行）
            order_result: dict = {}
            if self.order_executor.is_configured(signal.exchange):
                order_result = await self.order_executor.execute(
                    signal, sz, max_retries=self._order_max_retries
                )
                # 重试后仍失败：开仓立即触发 aggregator 重新决策，平仓改市价
                if not order_result.get("success"):
                    fail_reason = order_result.get("msg", "未知原因")
                    if signal.action == "open":
                        self.logger.warning(f"[execute] 开仓最终失败，触发重新决策: {signal.instId} — {fail_reason}")
                        asyncio.create_task(self._reaggregate_for_signal(signal, state, fail_reason))
                    else:
                        self.logger.warning(f"[execute] 平仓最终失败，转市价平仓: {signal.instId} — {fail_reason}")
                        asyncio.create_task(self.order_executor.close_position_market(
                            signal.exchange, signal.instId, signal.posSide, sz
                        ))
                # 下单成功且是限价单，注册心跳监控
                elif order_result.get("order_type_used") == "limit":
                    ord_id = order_result.get("ordId", "")
                    if ord_id:
                        await self.order_monitor.register(
                            signal=signal,
                            ord_id=ord_id,
                            sz=sz,
                            is_risk_close=(signal.action == "close"),
                        )
            else:
                self.logger.info(
                    f"[execute] {signal.exchange} 未配置 API Key，跳过实际下单: "
                    f"{signal.instId} {signal.action}/{signal.side}/{signal.posSide} sz={sz}"
                )

            await self.signal_publisher.publish(signal, rule_passed=True, sz=sz, order_result=order_result)
            self._put_event("signal", {
                **signal.model_dump(),
                "sz": sz,
                "rule_passed": True,
                "order_result": order_result,
                "timestamp": int(time.time()),
            })

        self._put_event("state", {
            "positions": current_positions,
            "orders": current_orders,
            "symbols": list(self.symbols),
        })
        return {
            "positions": current_positions,
            "orders": current_orders,
        }

    async def _end_node(self, state: Graph_state):
        """反思并压缩上下文，生成结构化 TradingReflection"""
        def get_last_content(messages):
            if not messages:
                return "无数据"
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "无数据")
                elif hasattr(msg, 'content'):
                    return msg.content
            return "无数据"

        fd_resp = get_last_content(state.get('fundamental_message') or [])
        chart_resp = get_last_content(state.get('chart_message') or [])
        risk_resp = get_last_content(state.get('risk_message') or [])
        agg_resp = get_last_content(state.get('aggregator_message') or [])

        if all(r == "无数据" for r in [fd_resp, chart_resp, risk_resp, agg_resp]):
            return {}

        # 只有本轮存在实际开仓或平仓信号时才计数，累积到 reflect_every_n 次才触发反思
        decision: Optional[AggregatorDecision] = state.get('aggregator_decision')
        has_action = decision and any(s.action != "hold" for s in decision.signals)
        if not has_action:
            self.logger.info("[end] 本轮无实际交易信号，跳过反思")
            return {}

        self._trade_round_count += 1
        if self._trade_round_count % self.reflect_every_n != 0:
            self.logger.info(f"[end] 有交易轮次 {self._trade_round_count}/{self.reflect_every_n}，暂不反思")
            return {}

        context = (
            f"基本面分析：{fd_resp}\n\n"
            f"技术分析：{chart_resp}\n\n"
            f"风险分析：{risk_resp}\n\n"
            f"综合决策：{agg_resp}\n\n"
            "请以 json 格式输出结构化反思报告。"
        )

        with open('../config/prompts/update_node.txt', 'r', encoding='utf-8') as f:
            sys_prompt = f.read()

        structured_llm = self.llm_client.update_model.with_structured_output(TradingReflection)
        try:
            reflection = structured_llm.invoke([
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": context}
            ])
        except Exception as e:
            self.logger.error(f"反思节点调用失败: {e}")
            return {}

        self.round_count += 1

        # 两个列表均为空说明本轮无有效反思内容，跳过存储
        if not reflection.mistakes_and_corrections and not reflection.successes_to_keep:
            self.logger.info("[end] 本轮反思内容不足，跳过存储")
            return {}

        # RAG：将本轮反思持久化到向量库
        try:
            self.reflection_store.add_reflection(
                reflection.model_dump(),
                state.get("symbols", []),
                state.get("timestamp", 0),
            )
        except Exception as e:
            self.logger.error(f"反思写入向量库失败: {e}")

        # 每轮都写入 LayeredMemory，保证 get_context_for_llm() 实时有内容
        memory_map = [
            (state.get('fundamental_message'), self.fundamental_memory),
            (state.get('chart_message'),       self.chart_memory),
            (state.get('risk_message'),        self.risk_memory),
            (state.get('aggregator_message'),  self.aggregator_memory),
        ]
        for msgs, memory in memory_map:
            for msg in (msgs or []):
                role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "type", "user")
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                if content:
                    memory.add_interaction(role, content)

        self._put_event("reflection", reflection.model_dump())
        result = {
            "fundamental_update": reflection,
            "chart_update":       reflection,
            "risk_update":        reflection,
            "aggregator_update":  reflection,
        }

        # 每 n 轮额外触发一次强制压缩（短期→长期），并清空 state 消息列表
        if self.round_count % self.compress_every_n == 0:
            for _, memory in memory_map:
                memory.force_compress()
            result.update({
                "fundamental_message": [],
                "chart_message":       [],
                "risk_message":        [],
                "aggregator_message":  [],
            })
            self.logger.info(f"第 {self.round_count} 轮，触发上下文压缩")
        return result

    def build_graph(self):
        def _fan_out(_state: Graph_state):
            return [
                Send("fundamental", _state),
                Send("chart", _state),
                Send("risk", _state),
            ]

        graph = (
            StateGraph(Graph_state)
            .add_node("fundamental", self._fundamental_node)
            .add_node("chart", self._chart_node)
            .add_node("risk", self._risk_node)
            .add_node("aggregator", self._aggregator_node)
            .add_node("execute", self._execute_node)
            .add_node("end", self._end_node)
            .add_conditional_edges(START, _fan_out, ["fundamental", "chart", "risk"])
            .add_edge("fundamental", "aggregator")
            .add_edge("chart", "aggregator")
            .add_edge("risk", "aggregator")
            .add_edge("aggregator", "execute")
            .add_edge("execute", "end")
            .add_edge("end", END)
            .compile()
        )
        return graph

    async def run(self):
        """启动 WebSocket 订阅，然后按时间间隔循环运行图，支持外部事件触发"""
        await self.start()

        run_interval = self.cf['data'].get('run_interval', 900)  # 默认15分钟
        self._trigger = asyncio.Event()

        initial_state: Graph_state = {
            "symbols": self.symbols,
            "timestamp": 0,
            "fundamental": {},
            "chart": {},
            "risk": {},
            "aggregator": {},
            "fundamental_message": [],
            "chart_message": [],
            "risk_message": [],
            "aggregator_message": [],
            "fundamental_update": None,
            "chart_update": None,
            "risk_update": None,
            "aggregator_update": None,
            "aggregator_decision": None,
            "positions": {},
            "orders": {},
            "skip_fundamental": False,
        }

        self._graph = self.build_graph()
        asyncio.create_task(self._symbol_refresh_loop())
        self.order_monitor.start()
        self.logger.info("workflow 启动")
        while True:
            try:
                await asyncio.wait_for(self._trigger.wait(), timeout=run_interval)
                self._trigger.clear()
                self.logger.info("外部触发，立即运行")
            except asyncio.TimeoutError:
                self.logger.info(f"定时触发（间隔 {run_interval}s）")

            self._graph_running = True
            try:
                async for chunk in self._graph.astream(initial_state, stream_mode="updates"):
                    for node_name, update in chunk.items():
                        self.logger.info(f"[{node_name}] 完成")
                        if not isinstance(update, dict):
                            continue
                        # 打印各节点最新的 assistant 消息
                        for field in ("fundamental_message", "chart_message", "risk_message", "aggregator_message"):
                            msgs = update.get(field)
                            if msgs:
                                last = msgs[-1]
                                content = last.get("content", "") if isinstance(last, dict) else getattr(last, "content", "")
                                if content:
                                    self.logger.info(f"[{node_name}][{field}]\n{content}")
                        # 打印反思结果
                        reflection = update.get("aggregator_update")
                        if reflection:
                            self.logger.info(f"[{node_name}][reflection]\n{reflection}")
            except Exception as e:
                self.logger.error(f"图执行异常: {e}")
            finally:
                self._graph_running = False
            await self._extract_price_watches()

    async def _reaggregate_for_signal(self, signal: TradeSignal, state: dict, fail_reason: str):
        """
        开仓失败或超时后，携带当轮三份报告和失败原因，立即让 aggregator 重新决策该品种。
        """
        def get_last_content(messages):
            if not messages:
                return "无数据"
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "无数据")
                elif hasattr(msg, 'content'):
                    return msg.content
            return "无数据"

        fd_report = get_last_content(state.get('fundamental_message') or [])
        chart_report = get_last_content(state.get('chart_message') or [])
        risk_report = get_last_content(state.get('risk_message') or [])

        retry_prompt = (
            f"针对品种 {signal.instId} 的开仓指令执行失败，原因：{fail_reason}。\n\n"
            f"请结合以下报告，重新给出对 {signal.instId} 的交易决策（可以调整价格、方向或改为观望）：\n\n"
            f"【基本面分析师报告】\n{fd_report}\n\n"
            f"【图表分析师报告】\n{chart_report}\n\n"
            f"【风险分析师报告】\n{risk_report}"
        )

        schema_hint = (
            "\n\n请以 JSON 格式输出结构化决策，必须包含以下英文字段：\n"
            "- signals: 交易信号列表，每项必须包含：\n"
            f"  - exchange: 交易所名称，固定填 {self.source}\n"
            "  - instId: 交易对，如 BTC-USDT-SWAP\n"
            "  - action: open（开仓）/ close（平仓）/ hold（观望）\n"
            "  - side: buy / sell\n"
            "  - posSide: long / short\n"
            "  - size_pct: 仓位占比 0.0~1.0\n"
            "  - leverage: 杠杆倍数（整数，最小1）\n"
            "  - order_type: market / limit\n"
            "  - px: 限价单价格字符串，市价单填 null\n"
            "  - sl_px: 止损价格字符串，必填\n"
            "  - tp_px: 止盈价格字符串，可为 null\n"
            "  - reason: 决策依据说明\n"
            "- market_summary: 市场综合摘要（字符串）\n"
            "- confidence: 决策置信度 0.0~1.0（浮点数）"
        )
        try:
            structured_llm = self.llm_client.aggregator_model.with_structured_output(AggregatorDecision)
            new_decision = structured_llm.invoke([
                {"role": "user", "content": retry_prompt + schema_hint}
            ])
            self.logger.info(f"[reaggregate] {signal.instId} 重新决策完成: {new_decision}")
            # 执行新决策
            for new_signal in new_decision.signals:
                if new_signal.action == "hold":
                    continue
                if new_signal.exchange != self.source:
                    new_signal = new_signal.model_copy(update={"exchange": self.source})
                if self.order_executor.is_configured(new_signal.exchange):
                    try:
                        sz = await self.order_sizer.compute(
                            exchange=new_signal.exchange,
                            inst_id=new_signal.instId,
                            size_pct=new_signal.size_pct,
                        )
                    except Exception:
                        sz = 1.0
                    result = await self.order_executor.execute(new_signal, sz, max_retries=1)
                    self.logger.info(f"[reaggregate] 重新下单结果: {new_signal.instId} {result}")
        except Exception as e:
            self.logger.error(f"[reaggregate] {signal.instId} 重新决策失败: {e}")

    async def _on_open_order_timeout(self, signal: TradeSignal, ord_id: str, reason: str):
        """OrderMonitor 回调：开仓限价单超时，触发重新决策"""
        self.logger.warning(f"[order_timeout] {signal.instId} ordId={ord_id} 超时，触发重新决策")
        # 用空 state 触发，报告会取最近一次的内容（此时 state 已不可用，用空dict降级）
        await self._reaggregate_for_signal(signal, {}, reason)

    def _on_position_update(self):
        """持仓变化时由 position_tracker 回调，schedule 熔断检查"""
        asyncio.ensure_future(self._check_drawdown())

    async def _extract_price_watches(self):
        """
        从上一轮 chart/risk 报告中提取价格触发条件，更新到 chart_analyst 的监控列表。
        每次图运行结束后调用，新条件会完全替换旧条件。
        """
        chart_report = self._last_chart_report
        risk_report = self._last_risk_report
        if not chart_report and not risk_report:
            return
        prompt = (
            "请从以下分析报告中提取所有包含明确数值的价格触发条件，"
            "例如「当价格跌破 80000 时...」「若价格涨至 95000 则...」。\n"
            "忽略无具体数值的模糊表述。每条条件须包含：交易对、方向（above/below）、价格数值、简短描述。\n"
            "无明确条件时返回空列表。请以 json 格式输出结果。\n\n"
            f"【图表分析报告】\n{chart_report}\n\n"
            f"【风险分析报告】\n{risk_report}"
        )
        try:
            structured_llm = self.llm_client.aggregator_model.with_structured_output(WatchConditionList)
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: structured_llm.invoke([{"role": "user", "content": prompt}])
            )
            self.chart_analyst.update_price_watches(result.conditions)
            if result.conditions:
                self.logger.info(
                    f"[price_watch] 更新监控条件 {len(result.conditions)} 个: "
                    + ", ".join(f"{c.instId} {c.direction} {c.price}" for c in result.conditions)
                )
        except Exception as e:
            self.logger.warning(f"[price_watch] 提取价格条件失败: {e}")

    def _on_kline_bar(self, sym: str, bar: list) -> None:
        """chart_analyst 每次更新/新增 bar 时调用，实时推送给前端。"""
        try:
            self._put_event("kline_bar", {
                "instId": sym,
                "exchange": self.source,
                "bar": {
                    "time": int(bar[0]) // 1000,
                    "open": float(bar[1]),
                    "high": float(bar[2]),
                    "low": float(bar[3]),
                    "close": float(bar[4]),
                    "volume": float(bar[5]) if len(bar) > 5 else 0,
                },
            })
        except (IndexError, ValueError, TypeError):
            pass

    def _on_price_alert(self, sym: str, price: float, reason: str):
        """
        chart_analyst 的实时 tick 命中价格条件时回调（在事件循环中同步执行）。
        触发一次跳过基本面的紧急分析。
        """
        if self._graph_running:
            self.logger.debug(f"[price_alert] {sym} 价格条件触发但图正在运行，跳过")
            return
        self.logger.info(f"[price_alert] {sym}@{price} 触发条件「{reason}」，启动紧急分析")
        asyncio.ensure_future(self._run_emergency_analysis(sym))

    def _on_volatility(self, sym: str):
        """
        chart_analyst 检测到持仓品种 ATR 超限时调用（在事件循环中同步执行）。
        若图当前未运行，立即触发一次跳过基本面的紧急分析。
        """
        positions = self.position_tracker.get_positions()
        has_position = any(
            sym in key for key in positions
        )
        if not has_position:
            return
        if self._graph_running:
            self.logger.debug(f"[volatility] {sym} 波动触发但图正在运行，跳过")
            return
        self.logger.info(f"[volatility] {sym} 持仓品种剧烈波动，触发紧急分析")
        asyncio.ensure_future(self._run_emergency_analysis(sym))

    async def _run_emergency_analysis(self, trigger_sym: str):
        """跳过基本面分析师，对当前所有品种执行一次紧急分析"""
        if self._graph_running:
            return
        self._graph_running = True
        self.logger.info(f"[emergency] 由 {trigger_sym} 触发，开始紧急分析（跳过基本面）")
        emergency_state: Graph_state = {
            "symbols": self.symbols,
            "timestamp": int(time.time()),
            "fundamental": {},
            "chart": {},
            "risk": {},
            "aggregator": {},
            "fundamental_message": [],
            "chart_message": [],
            "risk_message": [],
            "aggregator_message": [],
            "fundamental_update": None,
            "chart_update": None,
            "risk_update": None,
            "aggregator_update": None,
            "aggregator_decision": None,
            "positions": {},
            "orders": {},
            "skip_fundamental": True,
        }
        try:
            async for chunk in self._graph.astream(emergency_state, stream_mode="updates"):
                for node_name, update in chunk.items():
                    self.logger.info(f"[emergency][{node_name}] 完成")
        except Exception as e:
            self.logger.error(f"[emergency] 紧急分析异常: {e}")
        finally:
            self._graph_running = False
        await self._extract_price_watches()

    async def _check_drawdown(self):
        """检查当前权益是否触发熔断，触发则市价平所有持仓"""
        exec_cf = self.cf.get('execution', {})
        exchanges = exec_cf.get('exchanges', {})
        active_exchange = "okx" if exchanges.get('okx', {}).get('enabled') else "binance"
        try:
            current_equity = await self.order_sizer.get_total_equity(active_exchange)
            if current_equity is None:
                return

            if current_equity > self._peak_equity:
                self._peak_equity = current_equity
                return

            passed, reason = self.rule_guard.check_drawdown(current_equity, self._peak_equity)
            if passed:
                return

            self.logger.warning(f"[drawdown] 熔断触发: {reason}，开始市价平所有持仓")
            positions = self.position_tracker.get_positions()
            for key, pos in positions.items():
                try:
                    exchange = "okx" if key.startswith("okx:") else "binance"
                    inst_id = pos.get("instId") or pos.get("symbol", "")
                    pos_side = pos.get("posSide", "long")
                    sz = abs(float(pos.get("pos") or pos.get("positionAmt") or 1))
                    if not inst_id:
                        continue
                    result = await self.order_executor.close_position_market(
                        exchange=exchange,
                        inst_id=inst_id,
                        pos_side=pos_side,
                        sz=sz,
                    )
                    self.logger.info(f"[drawdown] 平仓结果: {inst_id} {result}")
                except Exception as e:
                    self.logger.error(f"[drawdown] 平仓失败 {key}: {e}")
        except Exception as e:
            self.logger.error(f"[drawdown] 检查异常: {e}")

    async def _symbol_refresh_loop(self):
        """
        后台协程：定期重新拉取全量品种列表。
        仅在【无持仓】且【图未运行】时执行刷新，防止干扰正在进行的分析。
        若品种列表发生变化，停止旧订阅并以新列表重新订阅。
        刷新间隔由 config/settings.yaml data.symbol_refresh_interval 控制（默认 3600s）。
        """
        refresh_interval = self.cf['data'].get('symbol_refresh_interval', 3600)
        self.logger.info(f"[symbol_refresh] 启动，刷新间隔 {refresh_interval}s")
        while True:
            await asyncio.sleep(refresh_interval)

            if self._graph_running:
                self.logger.debug("[symbol_refresh] 图正在运行，跳过本次刷新")
                continue

            if self.position_tracker.get_positions():
                self.logger.debug("[symbol_refresh] 当前有持仓，跳过本次刷新")
                continue

            try:
                if self.source == "okx":
                    new_symbols = self.market_fetcher.get_okx_all_symbols(instType='SWAP')
                else:
                    new_symbols = self.market_fetcher.get_binance_all_symbols()
            except Exception as e:
                self.logger.warning(f"[symbol_refresh] 拉取品种列表失败: {e}")
                continue

            if not new_symbols:
                self.logger.warning("[symbol_refresh] 拉取到空品种列表，跳过")
                continue

            if set(new_symbols) == set(self.symbols):
                self.logger.debug("[symbol_refresh] 品种列表无变化，无需重订阅")
                continue

            added = set(new_symbols) - set(self.symbols)
            removed = set(self.symbols) - set(new_symbols)
            self.logger.info(
                f"[symbol_refresh] 品种列表变化 — 新增: {len(added)} 个，下线: {len(removed)} 个，重新订阅"
            )

            await self.chart_analyst.stop_subscription()
            self.symbols = new_symbols
            self.market_fetcher.all_symbols = new_symbols
            await self.chart_analyst.gather_data(symbols=self.symbols, interval=self.intervals)
            self.logger.info("[symbol_refresh] 重订阅完成")

    def trigger(self):
        """外部调用此方法立即触发一次分析"""
        if hasattr(self, '_trigger'):
            self._trigger.set()

if __name__ == "__main__":
    wf = workflow(source="okx")
    asyncio.run(wf.run())



