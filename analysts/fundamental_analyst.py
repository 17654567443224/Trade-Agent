import asyncio
import yaml
from langchain.tools import tool
from analysts.base_analyst import Base_Analyst, make_tool_logger
from data.fundamental_fetcher import Fundamental
from utils.logger_engine import LoggerEngine
from skills.odaily_plugin.tools import macro_analysis, market_sentiment, market_trend, odaily_news, token_trend, tomorrow_watch
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage

@tool
def analyze_macro_impact(symbols) -> str:
    """
    symbols: 交易对列表，比如：[BTC,ETH]
    宏观经济事件对加密市场影响分析
    """
    res = macro_analysis.analyze_macro_impact(symbols)
    return res

@tool
def get_market_sentiment() -> str:
    """
    CSI 综合情绪指标报告，含各子指标评分和 AI 解读提示
    """
    res = market_sentiment.get_market_sentiment()
    return res

@tool
def get_market_analysis() -> str:
    """
    加密市场分析 — 行情数据 + 宏观事件影响（合并版）
    """
    res = market_trend.get_market_trend_analysis()
    return res

@tool
def get_today_watch() -> str:
    """
    快讯中挑选最值得关注的内容并附信息源
    """
    res = odaily_news.get_today_watch()
    return res

@tool
def analyze_token_trend(symbols) -> str:
    """
    symbols: 交易对列表，比如：[BTC,ETH]
    代币多周期趋势分析
    """
    result = {}
    for i in symbols:
        res = token_trend.analyze_token_trend(i)
        result[i] = res
    return result

@tool
def get_tomorrow_watch():
    """获取明日值得关注的消息"""
    res = tomorrow_watch.get_tomorrow_watch()
    return res

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


TOOLS = {
    "crypto": [analyze_macro_impact, get_market_sentiment, get_market_analysis, get_today_watch,
               analyze_token_trend, get_tomorrow_watch]
}

class FundamentalAnalyst(Base_Analyst):
    """基本面分析师"""
    def __init__(self, llm_client, fundamental_fetcher: Fundamental,logger: LoggerEngine, source):
        super().__init__(llm_client, logger)
        self.logger = logger.get_logger("analysts.fundamental")
        self.source = source
        with open('../config/settings.yaml', 'r', encoding='utf-8') as f:
            self.cf = yaml.safe_load(f)
        self.fether = fundamental_fetcher
        self.tools = []
        self._build_tools()

    def _build_tools(self):
        if self.source in self.cf['data']['source']['crypto']:
            self.tools = TOOLS.get('crypto')

    @property
    def analyst_type(self) -> str:
        return "fundamental_analyst"

    def gather_data(self, symbols: list) -> dict:
        """收集基本面数据：估值、财务指标、行业对比等"""
        if self.source in self.cf['data']['source']['crypto']:
            if self.source == "okx":
                res = self.fether.get_data(symbols)
                return res
        return {}

    def create_agent(self):
        with open('../config/prompts/fundamental_analyst.txt', 'r', encoding='utf-8') as f:
            sys_prompt = f.read()
        llm = self.llm_client.fundamental_model
        agent = create_agent(
            model=llm,
            tools=self.tools,
            middleware=[make_tool_logger(self.logger), handle_tool_errors],
            system_prompt=sys_prompt,
            name="fundamental"
        )
        return agent













