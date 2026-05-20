import yaml
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document


class ReflectionStore:
    """
    基于 ChromaDB 的交易反思知识库

    每次 _end_node 生成 TradingReflection 后，将结构化内容分解为细粒度
    文档写入向量库；_aggregator_node 决策前按当前市场上下文语义检索，
    将历史教训和成功经验注入提示词。

    文档类型（metadata.type）：
        mistake         — 错误教训
        success         — 成功经验
        anti_overfitting — 防过拟合笔记
    """

    COLLECTION_NAME = "trading_reflections"

    def __init__(
        self,
        config_path: str = "../config/llm.yaml",
        db_path: str = "data/reflection_db",
    ):
        with open(config_path, "r", encoding="utf-8") as f:
            cf = yaml.safe_load(f)
        emb_sp = cf['llm']['embedding']
        emb_cfg = cf["embedding"][emb_sp]
        self._embeddings = OpenAIEmbeddings(
            model=emb_cfg["model_id"],
            base_url=emb_cfg["url"],
            api_key=emb_cfg["api_key"],
            check_embedding_ctx_length=False,
        )

        Path(db_path).mkdir(parents=True, exist_ok=True)
        self._store = Chroma(
            collection_name=self.COLLECTION_NAME,
            embedding_function=self._embeddings,
            persist_directory=db_path,
        )

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def add_reflection(
        self,
        reflection_dict: Dict[str, Any],
        symbols: List[str],
        timestamp: int,
    ) -> None:
        """将一次 TradingReflection 转为文档批量写入向量库"""
        ts_str = (
            datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
            if timestamp
            else datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        symbols_str = ",".join(symbols)
        docs: List[Document] = []

        # 错误教训
        for mistake in reflection_dict.get("mistakes_and_corrections", []):
            content = (
                f"[错误教训] {mistake.get('error_description', '')}\n"
                f"根本原因: {mistake.get('cause', '')}\n"
                f"纠正准则: {mistake.get('correction_guideline', '')}"
            )
            docs.append(Document(
                page_content=content,
                metadata={"type": "mistake", "symbols": symbols_str, "time": ts_str},
            ))

        # 成功经验
        for success in reflection_dict.get("successes_to_keep", []):
            content = (
                f"[成功经验] {success.get('success_description', '')}\n"
                f"有效原因: {success.get('why_it_worked', '')}\n"
                f"复用策略: {success.get('preservation_strategy', '')}"
            )
            docs.append(Document(
                page_content=content,
                metadata={"type": "success", "symbols": symbols_str, "time": ts_str},
            ))

        # 防过拟合笔记
        anti_note = reflection_dict.get("anti_overfitting_notes", "")
        if anti_note:
            docs.append(Document(
                page_content=f"[防过拟合] {anti_note}",
                metadata={"type": "anti_overfitting", "symbols": symbols_str, "time": ts_str},
            ))

        if docs:
            self._store.add_documents(docs)

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def query_similar(self, market_context: str, k: int = 5) -> str:
        """
        根据当前市场上下文检索最相关的历史反思

        Args:
            market_context: 当前市场描述（用于语义检索的 query 文本）
            k:              返回条数

        Returns:
            格式化字符串，可直接拼入提示词；库为空时返回空字符串
        """
        try:
            count = self._store._collection.count()
        except Exception:
            return ""

        if count == 0:
            return ""

        results = self._store.similarity_search(market_context, k=min(k, count))
        if not results:
            return ""

        lines = ["## 历史经验参考（RAG检索）"]
        for i, doc in enumerate(results, 1):
            meta = doc.metadata
            tag = {"mistake": "错误教训", "success": "成功经验", "anti_overfitting": "防过拟合"}.get(
                meta.get("type", ""), meta.get("type", "")
            )
            lines.append(
                f"\n### {i}. [{tag}]  {meta.get('time', '')}  ({meta.get('symbols', '')})"
            )
            lines.append(doc.page_content)

        return "\n".join(lines)
