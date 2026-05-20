import yaml


class RuleGuard:
    """硬规则风控，所有决策必须通过此检查才能执行"""
    def __init__(self):
        with open('../config/roleGuard.yaml', 'r', encoding='utf-8') as f:
            self.cf = yaml.safe_load(f)
        self.max_position_pct = self.cf['max_position_pct']
        self.max_drawdown_pct = self.cf['max_drawdown_pct']
        self.max_positions = self.cf['max_positions']
        self.max_leverage = self.cf.get('max_leverage', 10)
        self.max_sl_loss_pct = self.cf.get('max_sl_loss_pct', 0.10)

    def check_position_count(self, positions: dict) -> tuple:
        """检查持仓数量是否达到上限，达到则禁止新开仓"""
        count = len(positions)
        if count >= self.max_positions:
            return False, f"持仓数量 {count} 已达上限 {self.max_positions}，禁止新开仓"
        return True, ""

    def check_position_size(self, size_pct: float) -> tuple:
        """检查单笔仓位比例是否超限"""
        if size_pct > self.max_position_pct:
            return False, f"单笔仓位 {size_pct:.1%} 超过上限 {self.max_position_pct:.1%}"
        return True, ""

    def check_leverage(self, leverage: int) -> tuple:
        """检查杠杆倍数是否超过最大限制，超限时截断到最大值"""
        if leverage > self.max_leverage:
            return False, f"杠杆 {leverage}x 超过上限 {self.max_leverage}x，将使用最大值 {self.max_leverage}x"
        return True, ""

    def check_sl_px(
        self,
        sl_px: str | None,
        entry_px: float,
        pos_side: str,
        leverage: int,
    ) -> tuple[bool, str, str | None]:
        """
        校验止损价格是否考虑了杠杆影响。
        最大允许价格偏移 = max_sl_loss_pct / leverage。
        超出时自动修正为边界值，返回 (is_valid, reason, corrected_sl_px)。
        """
        if not sl_px or entry_px <= 0:
            return True, "", sl_px

        try:
            sl = float(sl_px)
        except ValueError:
            return True, "", sl_px

        max_move = self.max_sl_loss_pct / max(leverage, 1)

        if pos_side == "long":
            min_sl = entry_px * (1 - max_move)
            if sl < min_sl:
                corrected = str(round(min_sl, 6))
                return False, (
                    f"多头止损价 {sl} 距入场价 {entry_px} 偏移 "
                    f"{abs(sl - entry_px) / entry_px:.2%}，超过 {leverage}x 杠杆允许的 {max_move:.2%}，"
                    f"已修正为 {corrected}"
                ), corrected
        elif pos_side == "short":
            max_sl = entry_px * (1 + max_move)
            if sl > max_sl:
                corrected = str(round(max_sl, 6))
                return False, (
                    f"空头止损价 {sl} 距入场价 {entry_px} 偏移 "
                    f"{abs(sl - entry_px) / entry_px:.2%}，超过 {leverage}x 杠杆允许的 {max_move:.2%}，"
                    f"已修正为 {corrected}"
                ), corrected

        return True, "", sl_px

    def check_tp_px(
        self,
        tp_px: str | None,
        entry_px: float,
        pos_side: str,
    ) -> tuple[bool, str, str | None]:
        """
        校验止盈价格方向：多头 tp_px 必须高于入场价，空头必须低于入场价。
        方向错误时移除 tp_px（返回 None），避免反向触发。
        """
        if not tp_px or entry_px <= 0:
            return True, "", tp_px
        try:
            tp = float(tp_px)
        except ValueError:
            return True, "", tp_px

        if pos_side == "long" and tp <= entry_px:
            return False, f"多头止盈价 {tp} 应高于入场价 {entry_px}，已移除", None
        if pos_side == "short" and tp >= entry_px:
            return False, f"空头止盈价 {tp} 应低于入场价 {entry_px}，已移除", None
        return True, "", tp_px

    def check_drawdown(self, current_equity: float, peak_equity: float) -> tuple:
        """检查最大回撤是否触发熔断，触发则禁止所有交易"""
        if peak_equity <= 0:
            return True, ""
        drawdown = (peak_equity - current_equity) / peak_equity
        if drawdown >= self.max_drawdown_pct:
            return False, f"当前回撤 {drawdown:.1%} 触发熔断线 {self.max_drawdown_pct:.1%}，禁止所有交易"
        return True, ""
