import asyncio

import yaml
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage

from analysts.base_analyst import Base_Analyst, make_tool_logger
from utils.logger_engine import LoggerEngine


TOOLS = {
    "crypto": []
}

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
class RiskAnalyst(Base_Analyst):
    """风控管理"""
    def __init__(self, llm_client, logger: LoggerEngine, source):
        super().__init__(llm_client, logger)
        self.logger = logger.get_logger("analysts.risk")
        self.source = source
        self.positions = {}
        self.orders = {}
        with open('../config/settings.yaml', 'r', encoding='utf-8') as f:
            self.cf = yaml.safe_load(f)
        self.tools = []
        self._build_tools()

    @property
    def analyst_type(self) -> str:
        return "risk_analyst"

    def _build_tools(self):
        if self.source in self.cf['data']['source']['crypto']:
            self.tools = TOOLS.get('crypto')

    def gather_data(self, symbols: list) -> dict:
        positions = {k: v for k, v in self.positions.items() if k in symbols}
        orders = {k: v for k, v in self.orders.items() if k in symbols}
        return positions, orders

    def create_agent(self):
        with open('../config/prompts/risk_analyst.txt', 'r', encoding='utf-8') as f:
            sys_prompt = f.read()
        llm = self.llm_client.risk_model
        agent = create_agent(
            model=llm,
            tools=self.tools,
            middleware=[make_tool_logger(self.logger), handle_tool_errors],
            system_prompt=sys_prompt,
            name="risk"
        )
        return agent












