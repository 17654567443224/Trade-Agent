import yaml

from utils.logger_engine import LoggerEngine
from langchain_openai import ChatOpenAI

# 需要禁用 thinking 的模型前缀（非流式调用时必须设 enable_thinking=False）
_THINKING_MODEL_PREFIXES = ("qwen3", "qwq")

def _is_thinking_model(model_id: str) -> bool:
    return any(model_id.lower().startswith(p) for p in _THINKING_MODEL_PREFIXES)

def _make_chat_openai(model_id: str, base_url: str, api_key: str) -> ChatOpenAI:
    kwargs = dict(model=model_id, base_url=base_url, api_key=api_key)
    if _is_thinking_model(model_id):
        kwargs["extra_body"] = {"enable_thinking": False}
    return ChatOpenAI(**kwargs)

class LLMClient:
    def __init__(self, logger: LoggerEngine):
        self.logger = logger.get_logger("utils.llmclient")
        self.general = {}
        self.fundamental = {}
        self.chart = {}
        self.risk = {}
        self.aggregator = {}
        self.update = {}
        self.fundamental_model: ChatOpenAI | None = None
        self.chart_model: ChatOpenAI | None = None
        self.risk_model: ChatOpenAI | None = None
        self.aggregator_model: ChatOpenAI | None = None
        self.update_model: ChatOpenAI | None = None
        self._load_model()
        self._create_model()

    def _load_model(self):
        with open('../config/llm.yaml', 'r', encoding='utf-8') as f:
            self.cf = yaml.safe_load(f)
        modules = ['general', 'fundamental', 'chart', 'risk', 'aggregator', 'update']
        for module in modules:
            suppliers = self.cf['llm'][module]
            setattr(self, module, {
                s: self.cf['model_supplier'][s] for s in suppliers
            })

    def add_backup_model(self, role):
        if hasattr(self, role):
            target = getattr(self, role)
            for s, v in self.general.items():
                if s in target:
                    target[s] = list(dict.fromkeys(target[s]['model_id'] + v['model_id']))
                else:
                    target[s] = v
        else:
            self.logger.error(f"找不到这个role：{role}")

    def _create_model(self):
        modules = ['fundamental', 'chart', 'risk', 'aggregator', 'update']
        for module in modules:
            config_dict = getattr(self, module)
            first_key = None
            for k, v in list(config_dict.items()):
                if first_key is None:
                    first_key = k
                setattr(self, f'{module}_model', _make_chat_openai(
                    model_id=v['model_id'][0],
                    base_url=v['url'],
                    api_key=v['api_key']
                ))
            if first_key is not None:
                config_dict['using'] = {first_key: 0}

    def switch_model(self, role):
        target = getattr(self, role)
        k, v = next(iter(target['using'].items()))
        if v < len(target[k]['model_id']) - 1:
            target['using'][k] = v + 1
            setattr(self, role + "_model", _make_chat_openai(
                model_id=target[k]['model_id'][v + 1],
                base_url=target[k]['url'],
                api_key=target[k]['api_key']
            ))
        else:
            new_key = None
            it = iter(target)
            for key in it:
                if key == k:
                    new_key = next(it, None)
            if new_key:
                setattr(self, role + "_model", _make_chat_openai(
                    model_id=target[new_key]['model_id'][0],
                    base_url=target[new_key]['url'],
                    api_key=target[new_key]['api_key']
                ))
            else:
                self._create_model()
                self.logger.error("No available models")
