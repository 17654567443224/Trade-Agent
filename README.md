<div align="center">

# ⚡ Trade-Agent

**AI 驱动期货量化交易系统**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-MultiAgent-FF6B35?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

*三位 AI 分析师并行工作，一个首席工程师综合决策，实时盯盘、自我反思、持续进化*

</div>

---

## 概览

Trade-Agent 是一个完整的 AI 量化交易系统，将 **大语言模型的分析推理能力**与**专业的量化交易基础设施**深度融合。系统由多个专业 AI 分析师并行运行，各司其职，最终由聚合器做出综合决策，并通过自我反思机制在每次交易后持续学习进化。

```
市场行情 + 基本面数据
        ↓ 并行分析
┌──────────────────────────────────────┐
│  基本面分析师  │  图表分析师  │  风险分析师  │
│  宏观/情绪    │  技术指标    │  仓位/波动  │
└──────────────┴─────────────┴────────────┘
                    ↓ 汇总
              首席工程师 (Aggregator)
              结构化交易决策
                    ↓ 执行
         规则守卫 → 下单执行 → 仓位跟踪
                    ↓ 学习
              自我反思 & 记忆更新
```

---

## 核心亮点

### 多智能体并行架构
三位 AI 分析师基于 **LangGraph DAG** 完全并行运行，互不阻塞。每位分析师持有独立的分层记忆（短期 10 条 + 长期压缩摘要），在各自专业领域深入分析后，由聚合器综合所有报告生成最终决策。

### 自我反思与持续进化
每次有实际交易的轮次结束后，系统自动触发 **结构化反思**，通过 Pydantic 模型记录：
- 本轮犯了哪些错误、根本原因和纠正准则
- 哪些策略有效，值得保留
- 防止对特定市场条件过拟合的注意事项

反思内容写入 **RAG 向量库**，下一轮分析时自动检索注入上下文，真正实现跨轮次学习。

### 硬性风控熔断
在 LLM 决策之外，独立的 `RuleGuard` 模块提供不可绕过的风控保障：
- 最大持仓数量限制（默认 5 个）
- 单笔最大仓位比例（默认 20%）
- 回撤熔断线（默认 45%）
- 最大杠杆倍数（默认 10x）
- 单笔止损最大亏损比例（默认 10%）

### 智能标的筛选
`symbol_select` 模块从全市场自动筛选最值得关注的交易标的：取**涨幅最高、居中、最低**各 N 个品种的并集，确保捕捉趋势行情的同时兼顾均值回归机会。

### 实时 WebSocket 全栈监控
前后端通过 WebSocket 实时同步，所有分析过程、决策、信号、仓位变化均以事件流推送到前端仪表盘，零延迟可观测。

---

## 系统架构

### 后端模块

| 模块 | 路径 | 职责 |
|------|------|------|
| **工作流编排** | `orchestration/workflow.py` | LangGraph DAG，节点定义，状态管理 |
| **基本面分析师** | `analysts/fundamental_analyst.py` | 宏观/舆情分析，调用 Odaily 新闻/情绪/日历工具 |
| **图表分析师** | `analysts/chart_analyst.py` | TA-Lib 技术指标，OKX/Binance WebSocket K 线 |
| **风险分析师** | `analysts/risk_analyst.py` | 仓位风险、波动率评估 |
| **聚合器** | `chief_engineer/aggregator.py` | 综合三位分析师报告，结构化输出交易决策 |
| **分层记忆** | `chief_engineer/compact.py` | 短期 10 条 + 长期压缩摘要 + 元摘要，Token 预算管理 |
| **反思引擎** | `chief_engineer/update_llm.py` | 结构化记录交易得失，写入向量库 |
| **规则守卫** | `execution/rule_guard.py` | 硬性风控熔断，不依赖 LLM |
| **订单执行** | `execution/order_executor.py` | OKX/Binance 下单，限价单超时自动撤单 |
| **仓位跟踪** | `execution/position_tracker.py` | 多交易所 Private WS，实时同步仓位和订单 |
| **信号发布** | `execution/signal_publisher.py` | asyncio.Queue + 可选 Webhook 外部推送 |
| **标的筛选** | `orchestration/symbol_select.py` | 多维度涨跌幅指标自动筛选活跃标的 |
| **查询引擎** | `orchestration/query_runner.py` | 支持自然语言提问，流式返回分析结果 |
| **API 服务** | `api/server.py` | FastAPI REST + WebSocket 事件总线 |
| **LLM 客户端** | `utils/llm_client.py` | 多模型自动降级（通义千问 → GLM → DeepSeek） |

### LLM 供应商与模型降级链

```
主力: 通义千问 (阿里云百炼)
  ├── qwen3.5-27b
  ├── qwen-max
  └── qwen3.6-plus
        ↓ 自动降级
备用: 火山方舟 (ByteDance Ark)
  ├── doubao-seed-2-0-pro
  ├── glm-4-7
  └── deepseek-v3
```

### 前端界面

| 组件 | 功能 |
|------|------|
| `KlineChart` | TradingView 风格 K 线图，实时更新 |
| `AgentReports` | 三位分析师实时报告面板 |
| `AggregatorPanel` | 聚合决策与置信度展示 |
| `SignalFeed` | 实时交易信号流 |
| `PositionsTable` | 当前持仓明细 |
| `OrdersTable` | 订单历史与状态 |
| `ReflectionLog` | AI 自我反思日志 |
| `QueryPanel` | 自然语言对话查询，流式回答 |

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- TA-Lib（需单独安装 C 库）

### 安装依赖

```bash
# 克隆仓库
git clone https://github.com/你的用户名/trade-agent.git
cd trade-agent

# 安装 Python 依赖
pip install langchain langgraph langchain-openai talib-binary tiktoken \
            aiohttp pydantic pyyaml fastapi uvicorn faiss-cpu

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 配置

```bash
# 复制配置模板
cp config/settings.yaml.example config/settings.yaml
cp config/llm.yaml.example config/llm.yaml

# 编辑配置，填入你的 API 密钥
vim config/settings.yaml   # 填入 OKX/Binance API 密钥
vim config/llm.yaml        # 填入 LLM 供应商 API 密钥
```

**`config/settings.yaml` 关键配置：**

```yaml
execution:
  exchanges:
    okx:
      enabled: True
      api_key: "YOUR_OKX_API_KEY"
      passphrase: "YOUR_OKX_PASSPHRASE"
      secret_key: "YOUR_OKX_SECRET_KEY"
      flag: "1"   # "0"=实盘, "1"=模拟盘  ← 建议先用模拟盘测试
```

### 启动

```bash
# 一键启动后端（API 服务 + 交易工作流）
python run_server.py
# → http://localhost:8000
# → http://localhost:8000/docs  (API 文档)

# 启动前端开发服务器（新终端）
cd frontend && npm run dev
# → http://localhost:5173
```

---

## 配置说明

### `config/settings.yaml`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `data.interval` | `1m` | K 线周期 |
| `data.run_interval` | `600` | 工作流轮次间隔（秒） |
| `data.reflect_every_n` | `5` | 每 N 次有交易轮次触发一次反思 |
| `data.compress_every_n` | `5` | 每 N 轮压缩一次上下文记忆 |
| `data.warmup_kline_count` | `20` | 图表分析师预热所需最少 K 线数 |
| `execution.exchanges.okx.flag` | `"1"` | `"0"`=实盘 / `"1"`=模拟盘 |

### `config/roleGuard.yaml`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_positions` | `5` | 最大同时持仓数 |
| `max_position_pct` | `0.2` | 单仓最大占比 20% |
| `max_drawdown_pct` | `0.45` | 回撤熔断线 45% |
| `max_leverage` | `10` | 最大杠杆倍数 |
| `max_sl_loss_pct` | `0.10` | 止损触发时单笔最大亏损比例 |

---

## API 接口

启动后访问 `http://localhost:8000/docs` 查看完整 API 文档。

**主要接口：**

```
GET  /api/status          # 系统运行状态
GET  /api/positions        # 当前持仓
GET  /api/orders           # 订单历史
GET  /api/signals          # 最近交易信号
GET  /api/reflections      # AI 反思记录
POST /api/query            # 自然语言提问
     {"question": "BTC 当前趋势如何？", "instId": "BTC-USDT-SWAP"}

WS   /ws                   # 实时事件流
```

**WebSocket 事件类型：**

| 类型 | 说明 |
|------|------|
| `snapshot` | 系统全量状态快照 |
| `analyst` | 分析师实时报告 |
| `decision` | 聚合决策结果 |
| `signal` | 交易信号 |
| `kline` | K 线更新 |
| `reflection` | 反思记录 |
| `query_*` | 查询流式响应 |

---

## 项目结构

```
trade-agent/
├── analysts/               # AI 分析师
│   ├── base_analyst.py     # 抽象基类
│   ├── chart_analyst.py    # 图表技术分析
│   ├── fundamental_analyst.py  # 基本面分析
│   └── risk_analyst.py     # 风险评估
├── chief_engineer/         # 决策核心
│   ├── aggregator.py       # 聚合器
│   ├── compact.py          # 分层记忆系统
│   ├── reflection_store.py # 反思 RAG 向量库
│   └── update_llm.py       # 自我反思引擎
├── execution/              # 执行层
│   ├── signal_model.py     # Pydantic 信号模型
│   ├── order_executor.py   # 下单执行
│   ├── position_tracker.py # 仓位跟踪
│   ├── rule_guard.py       # 风控熔断
│   └── order_monitor.py    # 订单监控
├── orchestration/          # 编排层
│   ├── workflow.py         # LangGraph DAG
│   ├── query_runner.py     # 查询引擎
│   └── symbol_select.py    # 标的筛选
├── data/                   # 数据层
│   ├── market_data_fetcher.py   # 行情 WebSocket
│   └── fundamental_fetcher.py  # 基本面数据
├── api/                    # API 层
│   ├── server.py           # FastAPI 服务
│   └── ws_manager.py       # WebSocket 连接管理
├── frontend/               # React 前端
├── config/                 # 配置文件
│   ├── settings.yaml.example
│   ├── llm.yaml.example
│   ├── roleGuard.yaml
│   └── prompts/            # AI 系统提示词
├── SDK/                    # 交易所 SDK
│   ├── okx/
│   └── binance/
├── utils/
│   ├── llm_client.py       # 多模型客户端
│   └── logger_engine.py    # 日志引擎
├── run_server.py           # 统一启动入口
└── test.py                 # 单元测试
```

---

## 风险提示

> **重要声明**：本项目仅供学习和研究使用。交易具有极高风险，AI 模型的分析结果不构成投资建议。在使用实盘交易功能前，请充分了解相关风险，并在模拟盘充分测试后谨慎操作。作者不对任何交易损失承担责任。

**强烈建议：**
- 首次使用请将 `flag` 设置为 `"1"`（模拟盘）
- 充分回测并理解系统行为后再切换实盘
- 合理设置 `roleGuard.yaml` 中的风控参数

---

## Contributing

欢迎提交 Issue 和 Pull Request。在贡献代码前，请确保：
1. 不在代码中硬编码任何 API 密钥
2. 配置变更同步更新 `.example` 文件
3. 运行 `python test.py` 确认基础功能正常

---

<div align="center">

Built with LangGraph · FastAPI · React · TA-Lib

</div>
