import asyncio
import logging
from typing import Optional

from SDK.okx.Account import AccountAPI as OkxAccountAPI
from SDK.okx.Trade import TradeAPI as OkxTradeAPI
from SDK.binance.um_futures import UMFutures
from execution.signal_model import TradeSignal


class OrderExecutor:
    """
    将 TradeSignal 转换为实际交易所订单并提交。
    支持 OKX (SWAP) 和 Binance (U本位合约)。

    OKX:
      - place_order 下主单，attachAlgoOrds 附加 TP/SL
      - close 动作使用 reduceOnly=true

    Binance:
      - new_order 下主单
      - TP/SL 以独立的 TAKE_PROFIT_MARKET / STOP_MARKET 订单提交
      - hedge_mode=True 时传 positionSide；否则单向持仓模式
    """

    def __init__(
        self,
        okx_api_key: str = "",
        okx_secret_key: str = "",
        okx_passphrase: str = "",
        okx_flag: str = "0",
        okx_td_mode: str = "cross",
        binance_api_key: str = "",
        binance_secret_key: str = "",
        binance_rest_url: str = "https://fapi.binance.com",
        binance_hedge_mode: bool = True,
        logger=None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.okx_td_mode = okx_td_mode
        self.binance_hedge_mode = binance_hedge_mode

        self._okx_trade: Optional[OkxTradeAPI] = None
        self._okx_account: Optional[OkxAccountAPI] = None
        self._binance: Optional[UMFutures] = None

        if okx_api_key:
            self._okx_trade = OkxTradeAPI(
                api_key=okx_api_key,
                api_secret_key=okx_secret_key,
                passphrase=okx_passphrase,
                flag=okx_flag,
            )
            self._okx_account = OkxAccountAPI(
                api_key=okx_api_key,
                api_secret_key=okx_secret_key,
                passphrase=okx_passphrase,
                flag=okx_flag,
            )

        if binance_api_key:
            self._binance = UMFutures(
                key=binance_api_key,
                secret=binance_secret_key,
                base_url=binance_rest_url,
            )

    def is_configured(self, exchange: str) -> bool:
        """检查指定交易所是否已配置 API Key"""
        if exchange == "okx":
            return self._okx_trade is not None
        elif exchange == "binance":
            return self._binance is not None
        return False

    async def execute(self, signal: TradeSignal, sz: float, max_retries: int = 3) -> dict:
        """
        提交订单，失败时最多重试 max_retries 次。
        限价单优先：signal.px 有值用 limit，无值时从 mark price 构造 limit，再不行回退 market。
        返回 dict: {success, exchange, instId, ordId, msg, order_type_used}
        """
        for attempt in range(max_retries):
            try:
                if signal.exchange == "okx":
                    result = await self._place_okx(signal, sz)
                elif signal.exchange == "binance":
                    result = await self._place_binance(signal, sz)
                else:
                    return {
                        "success": False,
                        "exchange": signal.exchange,
                        "instId": signal.instId,
                        "msg": f"未知交易所: {signal.exchange}",
                    }

                if result.get("success"):
                    return result

                self.logger.warning(
                    f"[order_executor] 下单失败第 {attempt + 1}/{max_retries} 次 "
                    f"{signal.instId}: {result.get('msg')}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"[order_executor] 下单异常第 {attempt + 1}/{max_retries} 次 {signal.instId}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

        return {
            "success": False,
            "exchange": signal.exchange,
            "instId": signal.instId,
            "msg": f"重试 {max_retries} 次后仍失败",
        }

    # ------------------------------------------------------------------ #
    #  限价单价格辅助
    # ------------------------------------------------------------------ #

    async def _resolve_limit_px(self, signal: TradeSignal, loop) -> tuple[str, str]:
        """
        限价单优先策略：
        1. signal.px 有值 → 直接用 limit
        2. 无 px → 查 mark price 构造 limit（多头用 mark*1.001 略高买入，空头用 mark*0.999 略低卖出）
        3. mark price 也查不到 → 回退 market
        返回 (ord_type, px_str)
        """
        if signal.px:
            return "limit", signal.px

        mark_px = await self._get_mark_price(signal.exchange, signal.instId, loop)
        if mark_px and mark_px > 0:
            if signal.side == "buy":
                px = round(mark_px * 1.001, 6)
            else:
                px = round(mark_px * 0.999, 6)
            return "limit", str(px)

        return "market", ""

    async def _get_mark_price(self, exchange: str, inst_id: str, loop) -> Optional[float]:
        try:
            if exchange == "okx" and self._okx_account:
                from SDK.okx.PublicData import PublicAPI as OkxPublicAPI
                flag = getattr(self._okx_account, 'flag', '0')
                api = OkxPublicAPI(flag=flag)
                resp = await loop.run_in_executor(
                    None, lambda: api.get_mark_price(instType="SWAP", instId=inst_id)
                )
                data = resp.get("data", [])
                if data:
                    return float(data[0].get("markPx", 0))
            elif exchange == "binance" and self._binance:
                resp = await loop.run_in_executor(
                    None, lambda: self._binance.mark_price(symbol=inst_id)
                )
                return float(resp.get("markPrice", 0))
        except Exception as e:
            self.logger.warning(f"[order_executor] mark price 查询失败 {inst_id}: {e}")
        return None

    async def cancel_order(self, exchange: str, inst_id: str, ord_id: str) -> bool:
        """取消指定订单，返回是否成功"""
        loop = asyncio.get_event_loop()
        try:
            if exchange == "okx" and self._okx_trade:
                resp = await loop.run_in_executor(
                    None, lambda: self._okx_trade.cancel_order(instId=inst_id, ordId=ord_id)
                )
                return resp.get("code") == "0"
            elif exchange == "binance" and self._binance:
                await loop.run_in_executor(
                    None, lambda: self._binance.cancel_order(symbol=inst_id, orderId=int(ord_id))
                )
                return True
        except Exception as e:
            self.logger.error(f"[order_executor] 取消订单失败 {inst_id} {ord_id}: {e}")
        return False

    async def close_position_market(self, exchange: str, inst_id: str, pos_side: str, sz: float) -> dict:
        """市价平仓，用于熔断或超时风控"""
        from execution.signal_model import TradeSignal
        close_side = "sell" if pos_side == "long" else "buy"
        signal = TradeSignal(
            exchange=exchange,
            instId=inst_id,
            action="close",
            side=close_side,
            posSide=pos_side,
            size_pct=1.0,
            leverage=1,
            order_type="market",
            reason="风控强制平仓",
        )
        return await self.execute(signal, sz, max_retries=1)

    # ------------------------------------------------------------------ #
    #  OKX
    # ------------------------------------------------------------------ #

    async def _place_okx(self, signal: TradeSignal, sz: float) -> dict:
        if not self._okx_trade:
            return {"success": False, "exchange": "okx", "instId": signal.instId, "msg": "OKX 未配置 API Key"}

        loop = asyncio.get_event_loop()
        inst_id = signal.instId
        td_mode = self.okx_td_mode
        side = signal.side
        pos_side = signal.posSide
        reduce_only = "true" if signal.action == "close" else ""
        lever = str(signal.leverage)

        # 限价单优先
        ord_type, px = await self._resolve_limit_px(signal, loop)

        # 开仓前设置杠杆
        if signal.action == "open":
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._okx_account.set_leverage(
                        lever=lever,
                        mgnMode=td_mode,
                        instId=inst_id,
                        posSide=pos_side,
                    ),
                )
                self.logger.info(f"[order_executor] OKX 杠杆已设置: {inst_id} {lever}x ({td_mode}/{pos_side})")
            except Exception as e:
                self.logger.warning(f"[order_executor] OKX 设置杠杆失败 {inst_id}: {e}，继续下单")

        # 附加 TP/SL 算法单（-1 表示市价触发）
        attach_algo = []
        if signal.tp_px or signal.sl_px:
            algo: dict = {}
            if signal.tp_px:
                algo["tpTriggerPx"] = signal.tp_px
                algo["tpOrdPx"] = "-1"
            if signal.sl_px:
                algo["slTriggerPx"] = signal.sl_px
                algo["slOrdPx"] = "-1"
            attach_algo.append(algo)

        sz_str = str(int(sz))
        attach = attach_algo if attach_algo else None

        resp = await loop.run_in_executor(
            None,
            lambda: self._okx_trade.place_order(
                instId=inst_id,
                tdMode=td_mode,
                side=side,
                ordType=ord_type,
                sz=sz_str,
                posSide=pos_side,
                px=px,
                reduceOnly=reduce_only,
                attachAlgoOrds=attach,
            ),
        )

        if resp.get("code") == "0":
            ord_id = (resp.get("data") or [{}])[0].get("ordId", "")
            self.logger.info(
                f"[order_executor] OKX 下单成功: {inst_id} "
                f"{signal.action}/{side}/{pos_side} sz={sz_str} ordType={ord_type} ordId={ord_id}"
            )
            return {"success": True, "exchange": "okx", "instId": inst_id, "ordId": ord_id,
                    "msg": "ok", "order_type_used": ord_type}
        else:
            msg = resp.get("msg", str(resp))
            self.logger.error(f"[order_executor] OKX 下单失败: {inst_id} — {msg}")
            return {"success": False, "exchange": "okx", "instId": inst_id, "msg": msg}

    # ------------------------------------------------------------------ #
    #  Binance
    # ------------------------------------------------------------------ #

    async def _place_binance(self, signal: TradeSignal, sz: float) -> dict:
        if not self._binance:
            return {"success": False, "exchange": "binance", "instId": signal.instId, "msg": "Binance 未配置 API Key"}

        loop = asyncio.get_event_loop()
        bn_side = signal.side.upper()
        symbol = signal.instId

        # 限价单优先
        ord_type, px = await self._resolve_limit_px(signal, loop)
        bn_type = ord_type.upper()

        # 开仓前设置杠杆
        if signal.action == "open":
            lever = signal.leverage
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._binance.change_leverage(symbol=symbol, leverage=lever),
                )
                self.logger.info(f"[order_executor] Binance 杠杆已设置: {symbol} {lever}x")
            except Exception as e:
                self.logger.warning(f"[order_executor] Binance 设置杠杆失败 {symbol}: {e}，继续下单")

        kwargs: dict = {"quantity": sz}
        if self.binance_hedge_mode:
            kwargs["positionSide"] = signal.posSide.upper()
        if ord_type == "limit" and px:
            kwargs["price"] = px
            kwargs["timeInForce"] = "GTC"

        resp = await loop.run_in_executor(
            None,
            lambda: self._binance.new_order(symbol=symbol, side=bn_side, type=bn_type, **kwargs),
        )

        ord_id = str(resp.get("orderId", ""))
        self.logger.info(
            f"[order_executor] Binance 下单成功: {symbol} "
            f"{signal.action}/{bn_side}/{signal.posSide} sz={sz} ordType={ord_type} ordId={ord_id}"
        )

        if signal.tp_px or signal.sl_px:
            await self._place_binance_tp_sl(loop, signal)

        return {"success": True, "exchange": "binance", "instId": symbol, "ordId": ord_id,
                "msg": "ok", "order_type_used": ord_type}

    async def _place_binance_tp_sl(self, loop, signal: TradeSignal) -> None:
        """为 Binance 持仓附加独立止盈止损单"""
        close_side = "SELL" if signal.side.upper() == "BUY" else "BUY"
        symbol = signal.instId

        # closePosition=true 关闭整个方向仓位，不传 quantity
        common: dict = {"workingType": "MARK_PRICE", "closePosition": "true"}
        if self.binance_hedge_mode:
            common["positionSide"] = signal.posSide.upper()

        if signal.tp_px:
            tp_px = signal.tp_px
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._binance.new_order(
                        symbol=symbol,
                        side=close_side,
                        type="TAKE_PROFIT_MARKET",
                        stopPrice=tp_px,
                        **common,
                    ),
                )
                self.logger.info(f"[order_executor] Binance TP 已提交: {symbol} tp={tp_px}")
            except Exception as e:
                self.logger.error(f"[order_executor] Binance TP 提交失败 {symbol}: {e}")

        if signal.sl_px:
            sl_px = signal.sl_px
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._binance.new_order(
                        symbol=symbol,
                        side=close_side,
                        type="STOP_MARKET",
                        stopPrice=sl_px,
                        **common,
                    ),
                )
                self.logger.info(f"[order_executor] Binance SL 已提交: {symbol} sl={sl_px}")
            except Exception as e:
                self.logger.error(f"[order_executor] Binance SL 提交失败 {symbol}: {e}")
