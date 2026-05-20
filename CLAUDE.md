
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Trade-Agent is an AI-powered quantitative trading system for cryptocurrency futures markets. It uses a multi-agent LangChain framework where specialized LLM analysts (Fundamental, Chart, Risk) run in parallel, feed reports to an Aggregator, and a self-reflection module learns from outcomes.

## Commands

```bash
# Run tests (TA-Lib ATR calculation smoke test)
python test.py

# Main entry point (stub - orchestration is launched via workflow)
python main.py

# Run the workflow directly (primary execution path)
python orchestration/workflow.py
```

**Dependencies**: `langchain`, `langchain-openai`, `talib`, `tiktoken`, `aiohttp`, `pydantic`, `pyyaml`

## Architecture

### Multi-Agent DAG Workflow (`orchestration/workflow.py`)

```
[Market Data + Fundamental Data]
        ↓ (parallel)
┌──────────────┬──────────────┬──────────────┐
│ Fundamental  │    Chart     │     Risk     │
│   Analyst    │   Analyst    │   Analyst    │
└──────┬───────┴──────┬───────┴──────┬───────┘
       └──────────────▼──────────────┘
                 Aggregator
              (Chief Engineer)
                    ↓
           Update/Reflection Node
              (Self-Learning)
```

The workflow state is a `TypedDict` holding `symbols`, `timestamp`, per-analyst data, per-analyst `LayeredMemory` message histories, aggregated decision, and current `positions`/`orders`.

### Key Components

| Path | Role |
|---|---|
| `analysts/base_analyst.py` | Abstract base: loads prompts from `config/prompts/`, provides LLM client |
| `analysts/fundamental_analyst.py` | Macro/sentiment analysis; uses Odaily tools (news, sentiment, calendar) |
| `analysts/chart_analyst.py` | Technical analysis via TA-Lib on OKX/Binance K-line WebSocket data |
| `analysts/risk_analyst.py` | Position and volatility risk evaluation |
| `chief_engineer/aggregator.py` | Synthesizes all analyst reports into a final trading decision |
| `chief_engineer/compact.py` | Hierarchical memory: short-term (10 msgs) + long-term compressed summaries |
| `chief_engineer/update_llm.py` | Self-reflection: learns mistakes/successes via `TradingReflection` Pydantic model |
| `data/market_data_fetcher.py` | Async WebSocket K-line streaming from OKX and Binance Futures |
| `data/fundamental_fetcher.py` | Funding rates, open interest, data dedup/cleaning |
| `execution/rule_guard.py` | Hard circuit breakers (max drawdown, position limits) |
| `execution/fallback_strategy.py` | MA crossover fallback if LLM analysis fails |
| `utils/llm_client.py` | Unified LLM client with multi-model fallback (Doubao → GLM-4 → DeepSeek) |
| `utils/logger_engine.py` | Singleton logger: rotating files (50MB/10 backups), optional WebSocket broadcast |

### Configuration

| File | Purpose |
|---|---|
| `config/llm.yaml` | LLM provider + model IDs per analyst role; Huoshan (ByteDance Ark) endpoint |
| `config/settings.yaml` | Data sources (`okx`, `binance`), interval (`15m`), K-line count (100) |
| `config/roleGuard.yaml` | Risk limits: max 5 positions, 20% per trade, 45% drawdown circuit breaker |
| `config/prompts/*.txt` | System prompts loaded by each analyst at runtime |

### LLM Provider

All analysts use the Huoshan (ByteDance Ark) endpoint (`https://ark.cn-beijing.volces.com/api/v3`) with automatic fallback across:
1. `doubao-seed-2-0-pro-260215`
2. `glm-4-7-251222`
3. `deepseek-v3-2-251201`

### Memory System (`chief_engineer/compact.py`)

`LayeredMemory` maintains per-analyst conversation history:
- **Short-term**: last 10 messages (raw)
- **Long-term**: up to 20 compressed summaries
- **Meta-summary**: summary-of-summaries, updated every 5 compressions
- Token budget enforced via `tiktoken`

### Self-Reflection (`chief_engineer/update_llm.py`)

After each trading cycle, the `_end_node` uses a structured `TradingReflection` Pydantic model to record:
- `mistakes_and_corrections` — error description, cause, correction guideline
- `successes_to_keep` — what worked and why
- `anti_overfitting_notes` — guards against overfitting specific market conditions
