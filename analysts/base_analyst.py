import logging
from abc import ABC, abstractmethod
from pathlib import Path

from langchain.agents.middleware import wrap_tool_call

from utils.llm_client import LLMClient
from utils.logger_engine import LoggerEngine


def make_tool_logger(logger: logging.Logger):
    """
    返回一个 wrap_tool_call middleware，在每次工具调用前记录工具名称和入参。
    用法：middleware=[make_tool_logger(self.logger), handle_tool_errors]
    """
    @wrap_tool_call
    async def _log_tool_call(request, handler):
        tool_call = request.tool_call or {}
        name = tool_call.get("name", "unknown")
        args = tool_call.get("args", {})
        logger.info(f"[tool_call] {name} | args={args}")
        return await handler(request)

    return _log_tool_call


class Base_Analyst(ABC):
    def __init__(self, llm_client: LLMClient, logger: LoggerEngine, prompt_dir: str = "config/prompts"):
        self.llm_client = llm_client
        self.prompt_dir = prompt_dir
        self.logger = logger.get_logger("analysts.base")

    @property
    @abstractmethod
    def analyst_type(self) -> str:
        """子类返回角色标识，如 'chart_analyst'"""
        pass

    @abstractmethod
    def create_agent(self):
        pass

    @abstractmethod
    async def gather_data(self, **kwargs) -> dict:
        """子类实现：获取分析所需数据，返回字典"""
        pass

    def _load_prompt(self) -> str:
        """从 config/prompts/{analyst_type}.txt 加载系统提示词"""
        prompt_file = Path(self.prompt_dir + '/' + f"{self.analyst_type}.txt")
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        raise FileNotFoundError(f"找不到提示词文件: {prompt_file}")





