from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator, field_validator

# 合法的 (action, side, posSide) 组合：
#   开多: open  + buy  + long
#   开空: open  + sell + short
#   平多: close + sell + long
#   平空: close + buy  + short
#   持仓不动: hold（side/posSide 取值不限，不实际下单）
_VALID_COMBOS = {
    ("open",  "buy",  "long"),
    ("open",  "sell", "short"),
    ("close", "sell", "long"),
    ("close", "buy",  "short"),
}


class TradeSignal(BaseModel):
    exchange: str = Field(description="交易所名称，如 okx / binance")
    instId: str = Field(description="交易对，按交易所格式，如 BTC-USDT-SWAP (OKX) 或 BTCUSDT (Binance)")
    action: Literal["open", "close", "hold"] = Field(description="操作类型：开仓/平仓/持仓不动")
    side: Optional[Literal["buy", "sell"]] = Field(default=None, description="买入或卖出，hold 时为 null")
    posSide: Optional[Literal["long", "short"]] = Field(default=None, description="持仓方向：多/空，hold 时为 null")
    size_pct: float = Field(description="占可用余额百分比，0.0~1.0")
    leverage: int = Field(default=1, description="杠杆倍数，最小1倍", ge=1)

    @field_validator("size_pct", mode="before")
    @classmethod
    def clamp_size_pct(cls, v: float) -> float:
        """LLM 可能输出超出范围的值，自动截断到 [0, 1]"""
        return max(0.0, min(1.0, float(v)))
    order_type: Optional[Literal["market", "limit"]] = Field(default=None, description="订单类型：市价/限价，hold 时为 null")
    px: Optional[str] = Field(default=None, description="限价单价格")
    tp_px: Optional[str] = Field(default=None, description="止盈价格")
    sl_px: Optional[str] = Field(default=None, description="止损价格")
    reason: str = Field(description="LLM 推理说明")

    @model_validator(mode="after")
    def validate_direction(self) -> "TradeSignal":
        """校验 action/side/posSide 组合是否符合期货交易逻辑"""
        if self.action == "hold":
            return self
        combo = (self.action, self.side, self.posSide)
        if combo not in _VALID_COMBOS:
            raise ValueError(
                f"非法方向组合: action={self.action} side={self.side} posSide={self.posSide}。"
                f"合法组合: 开多(open/buy/long), 开空(open/sell/short), "
                f"平多(close/sell/long), 平空(close/buy/short)"
            )
        return self


class AggregatorDecision(BaseModel):
    signals: List[TradeSignal] = Field(description="交易信号列表")
    market_summary: str = Field(description="市场综合摘要")
    confidence: float = Field(description="决策置信度，0.0~1.0")

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))
