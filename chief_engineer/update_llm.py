import asyncio

import yaml
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
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
class Update_llm:
    """更新llm的update"""
    def __init__(self, llm_client, logger: LoggerEngine, source):
        self.llm_client = llm_client
        self.source = source
        with open('../config/settings.yaml', 'r', encoding='utf-8') as f:
            self.cf = yaml.safe_load(f)
        self.logger = logger.get_logger("chief_enginner.updatellm")
        self.tools = []
        self._build_tools()

    def _build_tools(self):
        if self.source in self.cf['data']['source']['crypto']:
            self.tools = TOOLS.get('crypto')

    def update(self, reports: list):
        """

        """
        return reports

    def create_agent(self):
        with open('config/prompts/update_node.txt', 'r', encoding='utf-8') as f:
            sys_prompt = f.read()
        llm = self.llm_client.update_model
        agent = create_agent(
            model=llm,
            tools=self.tools,
            middleware=[handle_tool_errors],
            system_prompt=sys_prompt,
            name="update_llm"
        )
        return agent





