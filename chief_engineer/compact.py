import json
from collections import deque
from datetime import datetime
from typing import List, Dict, Any, TypedDict

import tiktoken


class MemoryItem(TypedDict):
    """记忆项"""
    role: str  # user/assistant/system
    content: str
    timestamp: float
    metadata: Dict[str, Any]  # 额外的元数据


class ShortTermMemory:
    """短期记忆：保留最近N条完整消息"""

    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self.messages: deque = deque(maxlen=max_size)

    def add(self, role: str, content: str, metadata: Dict = None):
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().timestamp(),
            "metadata": metadata or {}
        })

    def get_all(self) -> List[MemoryItem]:
        """获取所有短期记忆"""
        return list(self.messages)

    def get_recent(self, n: int = None) -> List[MemoryItem]:
        """获取最近N条"""
        n = n or self.max_size
        return list(self.messages)[-n:]

    def clear(self):
        """清空短期记忆（转移到长期前调用）"""
        old_messages = list(self.messages)
        self.messages.clear()
        return old_messages

    def is_full(self) -> bool:
        """是否已满"""
        return len(self.messages) >= self.max_size

    def __len__(self):
        return len(self.messages)


class LongTermMemory:
    """长期记忆：存储压缩摘要"""

    def __init__(self, llm, max_summaries: int = 20):
        self.llm = llm
        self.max_summaries = max_summaries
        self.summaries: deque = deque(maxlen=max_summaries)

        # 元记忆：对摘要的摘要
        self.meta_summary: str = ""
        self.meta_summary_tokens: int = 0

    def add_summary(self, summary: str, source_period: str):
        """添加摘要"""
        self.summaries.append({
            "summary": summary,
            "source_period": source_period,
            "timestamp": datetime.now().timestamp(),
            "tokens": self._count_tokens(summary)
        })

        # 每5个摘要更新元摘要
        if len(self.summaries) % 5 == 0:
            self._update_meta_summary()

    def get_all_summaries(self) -> List[str]:
        """获取所有摘要"""
        return [s["summary"] for s in self.summaries]

    def get_recent_summaries(self, n: int = 5) -> List[str]:
        """获取最近N个摘要"""
        return [s["summary"] for s in list(self.summaries)[-n:]]

    def get_meta_summary(self) -> str:
        """获取元摘要（摘要的摘要）"""
        return self.meta_summary if self.meta_summary else "暂无长期记忆"

    def _update_meta_summary(self):
        """更新元摘要"""
        all_summaries = self.get_all_summaries()

        prompt = f"""将以下多个会话摘要合并为一个更高级的元摘要。
        不超过300字。

        摘要列表：
        {json.dumps(all_summaries, ensure_ascii=False, indent=2)}

        元摘要："""

        try:
            response = self.llm.invoke(prompt)
            self.meta_summary = response.content.strip()
            self.meta_summary_tokens = self._count_tokens(self.meta_summary)
        except:
            self.meta_summary = "元摘要生成失败"

    def _count_tokens(self, text: str) -> int:
        """计算token数"""
        try:
            encoder = tiktoken.encoding_for_model("gpt-4")
            return len(encoder.encode(text))
        except:
            return len(text) // 2  # 粗略估算

    def __len__(self):
        return len(self.summaries)


class LayeredMemory:
    """分层记忆系统：短期 + 长期"""

    def __init__(self, llm, short_term_size: int = 10, long_term_size: int = 20):
        self.short_term = ShortTermMemory(max_size=short_term_size)
        self.long_term = LongTermMemory(llm, max_summaries=long_term_size)
        self.llm = llm

        # 统计信息
        self.total_interactions = 0
        self.compression_count = 0

    def add_interaction(
            self,
            role: str,
            content: str,
            metadata: Dict = None
    ):
        """添加交互"""
        self.short_term.add(role, content, metadata)
        self.total_interactions += 1

        # 短期记忆满了，自动压缩到长期
        if self.short_term.is_full():
            self._compress_to_long_term()

    def _compress_to_long_term(self):
        """将短期记忆压缩到长期"""
        old_messages = self.short_term.clear()

        if not old_messages:
            return

        # 生成摘要
        prompt = f"""压缩以下对话为简洁摘要。
        不超过200字。

        对话：
        {self._format_messages(old_messages)}

        摘要："""

        try:
            response = self.llm.invoke(prompt)
            summary = response.content.strip()
        except:
            summary = f"对话摘要生成失败 (消息数: {len(old_messages)})"

        # 计算时间范围
        timestamps = [m["timestamp"] for m in old_messages]
        period = f"{datetime.fromtimestamp(min(timestamps)).strftime('%H:%M')} - {datetime.fromtimestamp(max(timestamps)).strftime('%H:%M')}"

        # 存入长期记忆
        self.long_term.add_summary(summary, period)
        self.compression_count += 1

    def get_context_for_llm(self, max_tokens: int = 4000) -> str:
        """获取适合传给LLM的上下文"""
        parts = []

        # 1. 元摘要（如果存在）
        meta = self.long_term.get_meta_summary()
        if meta and meta != "暂无长期记忆":
            parts.append(f"## 历史模式总结\n{meta}")

        # 2. 最近几个摘要
        recent_summaries = self.long_term.get_recent_summaries(5)
        if recent_summaries:
            parts.append("## 近期摘要\n" + "\n".join(f"- {s}" for s in recent_summaries))

        # 3. 当前短期记忆
        short_term_msgs = self.short_term.get_all()
        if short_term_msgs:
            parts.append("## 最新对话\n" + self._format_messages(short_term_msgs))

        context = "\n\n".join(parts)

        # Token控制：如果超限，裁剪最旧的内容
        tokens = self._count_tokens(context)
        if tokens > max_tokens:
            context = self._truncate_to_fit(context, max_tokens)

        return context

    def get_structured_context(self) -> Dict:
        """获取结构化的上下文"""
        return {
            "meta_summary": self.long_term.get_meta_summary(),
            "recent_summaries": self.long_term.get_recent_summaries(5),
            "short_term_messages": [
                {"role": m["role"], "content": m["content"]}
                for m in self.short_term.get_all()
            ],
            "stats": {
                "total_interactions": self.total_interactions,
                "compression_count": self.compression_count,
                "short_term_size": len(self.short_term),
                "long_term_size": len(self.long_term),
                "estimated_tokens": self._count_tokens(self.get_context_for_llm())
            }
        }

    def force_compress(self):
        """强制压缩（不管短期是否满）"""
        if len(self.short_term) > 0:
            self._compress_to_long_term()

    def clear_all(self):
        """清空所有记忆"""
        self.short_term.clear()
        self.long_term = LongTermMemory(self.llm, self.long_term.max_summaries)
        self.total_interactions = 0
        self.compression_count = 0

    def _format_messages(self, messages: List[MemoryItem]) -> str:
        """格式化消息为文本"""
        lines = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # 根据角色格式化
            if role == "user":
                lines.append(f"👤 用户: {content}")
            elif role == "assistant":
                lines.append(f"🤖 助手: {content}")
            elif role == "system":
                lines.append(f"⚙️ 系统: {content}")
            else:
                lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _count_tokens(self, text: str) -> int:
        """计算token数"""
        try:
            encoder = tiktoken.encoding_for_model("gpt-4")
            return len(encoder.encode(text))
        except:
            return len(text) // 2

    def _truncate_to_fit(self, context: str, max_tokens: int) -> str:
        """裁剪上下文到指定token数"""
        encoder = tiktoken.encoding_for_model("gpt-4")
        tokens = encoder.encode(context)

        if len(tokens) <= max_tokens:
            return context

        # 从头部裁剪
        truncated_tokens = tokens[-max_tokens:]
        return encoder.decode(truncated_tokens)