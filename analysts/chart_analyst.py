import asyncio
import time
from collections import deque
from typing import Callable, Dict, Optional

import numpy as np
import yaml
from langchain.tools import tool
import talib
from analysts.base_analyst import Base_Analyst, make_tool_logger
from data.market_data_fetcher import Market_Data
from utils.logger_engine import LoggerEngine
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage

@wrap_tool_call
async def handle_tool_errors(request, handler):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await handler(request)
        except Exception as e:
            if attempt == max_retries - 1:
                return ToolMessage(
                    content=f"重试 {max_retries} 次后仍失败，请检查输入是否正确，如果输入错误请改正并重试，否则跳过该工具: {e}",
                    tool_call_id=request.tool_call["id"]
                )
            await asyncio.sleep(1)
    return ToolMessage(
        content="工具执行异常，跳过该工具",
        tool_call_id=request.tool_call["id"]
    )

@tool
def get_indicator_arg(indicator_name: str) -> str:
    """
    获取 TA-Lib 指标所需的参数名称及说明。使用 get_indicator 前先调用此工具确认参数。

    Args:
        indicator_name: 指标名称（英文大写），如 'ATR', 'RSI', 'MACD', 'BBANDS'

    Returns:
        该指标的参数文档字符串
    """
    indicator_fun = getattr(talib, indicator_name)
    return indicator_fun.__doc__ or ""


@tool
def get_indicator(indicator_name: str, params: dict) -> str:
    """
    通过 TA-Lib 库计算技术指标。使用前先用 get_indicator_arg 查询所需参数。

    Args:
        indicator_name: 指标名称（英文大写），如 'MA', 'RSI', 'MACD', 'BBANDS', 'ATR' 等
        params: 指标所需参数字典，key 为参数名，value 为对应值。
                价格序列用 list 传入。
                例如：
                  MA     → {"real": [1.0, 1.1, ...], "timeperiod": 20}
                  RSI    → {"real": [1.0, 1.1, ...], "timeperiod": 14}
                  MACD   → {"real": [1.0, 1.1, ...], "fastperiod": 12, "slowperiod": 26, "signalperiod": 9}
                  BBANDS → {"real": [1.0, 1.1, ...], "timeperiod": 20, "nbdevup": 2, "nbdevdn": 2}
                  ATR    → {"high": [...], "low": [...], "close": [...], "timeperiod": 14}

    Returns:
        计算结果的字符串；多输出指标（如MACD）按输出顺序返回
    """
    converted = {}
    for k, v in params.items():
        if isinstance(v, list):
            converted[k] = np.array(v, dtype=np.float64)
        else:
            converted[k] = v

    indicator_fun = getattr(talib, indicator_name)
    result = indicator_fun(**converted)

    def fmt(arr):
        arr = np.array(arr)
        valid = arr[~np.isnan(arr)]
        tail = valid.tolist() if len(valid) > 0 else []
        return [round(x, 12) for x in tail]

    if isinstance(result, tuple):
        return str({f"output_{i}": fmt(r) for i, r in enumerate(result)})
    return str(fmt(result))

TOOLS = {
    "crypto": [get_indicator_arg, get_indicator]
}

class ChartAnalyst(Base_Analyst):
    """图表分析师"""
    def __init__(self, llm_client, market_fetcher: Market_Data, logger: LoggerEngine, source):
        super().__init__(llm_client, logger)
        self.logger = logger.get_logger("analysts.chart")
        self.source = source
        with open('../config/settings.yaml', 'r', encoding='utf-8') as f:
            self.cf = yaml.safe_load(f)
        self.fether = market_fetcher
        self.tools = []
        self._build_tools()
        # K 线缓冲上限：取 llm_kline_count 与 warmup_kline_count 的较大值，
        # 再加 ATR 周期 + 5 的余量，防止内存无限增长
        _data_cf = self.cf.get('data', {})
        _kline_need = max(
            _data_cf.get('save_kline_count', 20),
            _data_cf.get('warmup_kline_count', 20),
        )
        _atr_period = _data_cf.get('volatility_atr_period', 14)
        self._kline_maxlen: int = _kline_need + _atr_period + 5
        self.kline_data: Dict[str, deque] = {}
        self.tick_data: Dict[str, float] = {}
        self._ws_tasks: list[asyncio.Task] = []
        # 实时 K 线推送
        self._kline_bar_callback: Optional[Callable[[str, list], None]] = None
        # 波动检测
        self._volatility_callback: Optional[Callable[[str], None]] = None
        self._volatility_cooldown: float = 300.0
        self._atr_multiplier: float = 1.3
        self._atr_period: int = 14
        self._last_volatility_trigger: Dict[str, float] = {}
        # 价格监控
        self._price_watches: Dict[str, list] = {}   # {sym: [(direction, price, reason)]}
        self._price_alert_callback: Optional[Callable[[str, float, str], None]] = None

    def _build_tools(self):
        if self.source in self.cf['data']['source']['crypto']:
            self.tools = TOOLS.get('crypto')

    @property
    def analyst_type(self) -> str:
        return "chart_analyst"

    async def gather_data(self, symbols: list, interval: list) -> dict:
        """启动 WebSocket 订阅（后台任务，不阻塞）"""
        if self.source in self.cf['data']['source']['crypto']:
            if self.source == "okx":
                self._ws_tasks.append(asyncio.create_task(self.fether.okx_kline_ws_loop(symbols=symbols, intervals=interval)))
                self._ws_tasks.append(asyncio.create_task(self.fether.mark_price_okx_ws_loop(symbols=symbols)))
                self.kl_queue = self.fether.ebs.subscribe('okx_kline')
                self.mk_queue = self.fether.ebs.subscribe('okx_mark_price')

            elif self.source == "binance":
                self._ws_tasks.append(asyncio.create_task(self.fether.binance_kline_ws_loop(symbols=symbols, intervals=interval)))
                self._ws_tasks.append(asyncio.create_task(self.fether.subscribe_binance_mark_price(symbols=symbols)))
                self.kl_queue = self.fether.ebs.subscribe('binance_kline')
                self.mk_queue = self.fether.ebs.subscribe('binance_mark_price')

            else:
                self.logger.error("无该交易所接口")
                return {}

            self._ws_tasks.append(asyncio.create_task(self._update_data()))
        else:
            self.logger.error("数据获取失败")
            return {}

    async def stop_subscription(self):
        """取消所有 WebSocket 订阅任务，清空K线缓存，为重新订阅做准备"""
        for task in self._ws_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._ws_tasks.clear()
        self.kline_data.clear()
        self.tick_data.clear()

    def create_agent(self):
        with open('../config/prompts/chart_analyst.txt', 'r', encoding='utf-8') as f:
            sys_prompt = f.read()
        llm = self.llm_client.chart_model
        agent = create_agent(
            model=llm,
            tools=self.tools,
            middleware=[make_tool_logger(self.logger), handle_tool_errors],
            system_prompt=sys_prompt,
            name="chart"
        )
        return agent

    async def _update_data(self):
        mk_task = asyncio.create_task(self._run_tick(self.mk_queue))
        try:
            while True:
                try:
                    data = await self.kl_queue.get()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"kl_queue.get error:{e}")
                    continue
                try:
                    if not data:
                        continue
                    for sym, kl in data.items():
                        if isinstance(kl[0], list):
                            for k in kl:
                                self._update_kline(sym, k)
                        else:
                            self._update_kline(sym, kl)

                except Exception as e:
                    self.logger.error(f'_update_kline error:{e}')
                finally:
                    self.kl_queue.task_done()
        finally:
            mk_task.cancel()

    async def _run_tick(self, mark_q: asyncio.Queue):
        while True:
            try:
                data = await mark_q.get()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f'tick q.get error: {e}')
                continue
            try:
                if not data:
                    continue
                for sym, price in data.items():
                    try:
                        px = float(price)
                        self.tick_data[sym] = px
                        self._check_price_alerts(sym, px)
                    except Exception as e:
                        self.logger.error(f'on_tick error {sym}: {e}')
            finally:
                mark_q.task_done()

    def set_price_alert_callback(self, callback: Callable[[str, float, str], None]):
        """注册价格条件触发回调，callback(sym, price, reason)"""
        self._price_alert_callback = callback

    def update_price_watches(self, conditions: list):
        """
        替换当前价格监控列表。
        conditions 为 WatchCondition 对象列表，每项含 instId/direction/price/reason。
        """
        self._price_watches.clear()
        for cond in conditions:
            sym = cond.instId
            self._price_watches.setdefault(sym, []).append(
                (cond.direction, float(cond.price), cond.reason)
            )

    def _check_price_alerts(self, sym: str, price: float):
        if not self._price_alert_callback or sym not in self._price_watches:
            return
        remaining, triggered = [], []
        for direction, threshold, reason in self._price_watches[sym]:
            hit = (direction == "above" and price >= threshold) or \
                  (direction == "below" and price <= threshold)
            if hit:
                triggered.append((threshold, reason))
            else:
                remaining.append((direction, threshold, reason))
        self._price_watches[sym] = remaining
        for threshold, reason in triggered:
            self.logger.info(
                f"[price_alert] {sym} 价格 {price} 触发条件「{reason}」(阈值={threshold})"
            )
            self._price_alert_callback(sym, price, reason)

    def set_kline_bar_callback(self, callback: Callable[[str, list], None]) -> None:
        """注册实时 K 线推送回调，每次 bar 更新（含当前 bar 滚动更新）时调用 callback(sym, bar_list)。"""
        self._kline_bar_callback = callback

    def set_volatility_callback(
        self,
        callback: Callable[[str], None],
        cooldown: float = 300.0,
        multiplier: float = 1.3,
        atr_period: int = 14,
    ):
        """注册波动触发回调。callback(sym) 在事件循环中同步调用。"""
        self._volatility_callback = callback
        self._volatility_cooldown = cooldown
        self._atr_multiplier = multiplier
        self._atr_period = atr_period

    def _check_and_fire_volatility(self, sym: str):
        """
        在新 K 线入队前调用，检测刚完成的 K 线 TR 是否超过 atr_multiplier × ATR(atr_period)。
        满足条件且冷却期已过时调用 _volatility_callback(sym)。
        """
        if not self._volatility_callback:
            return
        buf = self.kline_data.get(sym)
        # 需要 atr_period + 2 根已完成 K 线：atr_period 根用于计算 ATR，+1 根提供前收价，+1 根为当前完成K线
        min_len = self._atr_period + 2
        if not buf or len(buf) < min_len:
            return

        candles = list(buf)
        n = len(candles)

        # ATR：使用最后 atr_period 根 K 线（不含刚完成的最后一根）
        atr_start = n - self._atr_period - 1  # 含前一根用于计算 TR
        trs_for_atr = []
        for i in range(atr_start + 1, n - 1):
            h, l, pc = candles[i][2], candles[i][3], candles[i - 1][4]
            trs_for_atr.append(max(h - l, abs(h - pc), abs(l - pc)))
        if not trs_for_atr:
            return
        atr = sum(trs_for_atr) / len(trs_for_atr)
        if atr <= 0:
            return

        # 刚完成 K 线的 TR
        last, prev = candles[-1], candles[-2]
        current_tr = max(
            last[2] - last[3],
            abs(last[2] - prev[4]),
            abs(last[3] - prev[4]),
        )

        if current_tr <= self._atr_multiplier * atr:
            return

        # 冷却检查
        now = time.monotonic()
        if now - self._last_volatility_trigger.get(sym, 0.0) < self._volatility_cooldown:
            return

        self._last_volatility_trigger[sym] = now
        self._volatility_callback(sym)

    def _update_kline(self, sym: str, k: list):
        self.kline_data.setdefault(sym, deque(maxlen=self._kline_maxlen))
        buf = self.kline_data[sym]
        if buf and buf[-1][0] == k[0]:
            cur = buf[-1]
            cur[2] = max(cur[2], k[2])
            cur[3] = min(cur[3], k[3])
            cur[4] = k[4]
            cur[5] = k[5]
            if self._kline_bar_callback:
                self._kline_bar_callback(sym, cur)
        else:
            # 新 K 线到来，上一根 K 线刚完成，检测波动
            self._check_and_fire_volatility(sym)
            buf.append(k)
            if self._kline_bar_callback:
                self._kline_bar_callback(sym, k)










