import asyncio
import logging
import math
from typing import Optional

from SDK.okx.Account import AccountAPI as OkxAccountAPI
from SDK.binance.um_futures import UMFutures
from execution.contract_info import ContractInfoCache


class OrderSizer:
    """
    将 size_pct（占可用余额百分比）转换为实际下单数量（张数）。

    流程：
    1. 实时查询可用余额（USDT）
    2. 用当前标记价格估算每张合约价值
    3. sz = floor( 可用余额 × size_pct / (标记价格 × 合约面值) )

    OKX：
      - 余额：AccountAPI.get_account_balance(ccy='USDT') → data[0].details[].availEq
      - 标记价格：PublicData 或直接用信号中的 px；无 px 时从 OKX REST 取 markPx
      - 合约面值：ContractInfoCache.get_contract_size('okx', instId)

    Binance：
      - 余额：UMFutures.balance() → [{'asset':'USDT', 'availableBalance':...}]
      - 标记价格：UMFutures.mark_price(symbol) → markPrice
      - 合约面值：固定 1.0，下单单位直接是合约数量（USDT 价值）
      - 精度：ContractInfoCache.get_qty_precision('binance', symbol)
    """

    def __init__(
        self,
        contract_info: ContractInfoCache,
        okx_api_key: str = "",
        okx_passphrase: str = "",
        okx_secret_key: str = "",
        okx_flag: str = "0",
        binance_api_key: str = "",
        binance_secret_key: str = "",
        binance_rest_url: str = "https://fapi.binance.com",
        logger=None,
    ):
        self.contract_info = contract_info
        self.logger = logger or logging.getLogger(__name__)

        self._okx_account: Optional[OkxAccountAPI] = None
        self._binance_client: Optional[UMFutures] = None

        if okx_api_key:
            self._okx_account = OkxAccountAPI(
                api_key=okx_api_key,
                api_secret_key=okx_secret_key,
                passphrase=okx_passphrase,
                flag=okx_flag,
            )

        if binance_api_key:
            self._binance_client = UMFutures(
                key=binance_api_key,
                secret=binance_secret_key,
                base_url=binance_rest_url,
            )

    async def compute(
        self,
        exchange: str,
        inst_id: str,
        size_pct: float,
        mark_px: Optional[float] = None,
    ) -> float:
        """
        返回四舍五入后的合约张数（>=1，不足 1 张时返回 1）。
        mark_px：可选，外部传入标记价格；为 None 时自动查询。
        """
        loop = asyncio.get_event_loop()

        if exchange == "okx":
            return await self._compute_okx(loop, inst_id, size_pct, mark_px)
        elif exchange == "binance":
            return await self._compute_binance(loop, inst_id, size_pct, mark_px)
        else:
            self.logger.warning(f"[order_sizer] 未知交易所 {exchange}，返回 sz=1")
            return 1.0

    # ------------------------------------------------------------------ #
    #  OKX
    # ------------------------------------------------------------------ #

    async def _compute_okx(
        self, loop, inst_id: str, size_pct: float, mark_px: Optional[float]
    ) -> float:
        if not self._okx_account:
            self.logger.warning("[order_sizer] OKX 未配置 API Key，返回 sz=1")
            return 1.0

        # 1. 查可用余额
        try:
            resp = await loop.run_in_executor(
                None, lambda: self._okx_account.get_account_balance(ccy="USDT")
            )
            avail_eq = self._parse_okx_balance(resp)
        except Exception as e:
            self.logger.error(f"[order_sizer] OKX 余额查询失败: {e}，返回 sz=1")
            return 1.0

        # 2. 标记价格
        if mark_px is None:
            mark_px = await self._get_okx_mark_price(loop, inst_id)
        if not mark_px or mark_px <= 0:
            self.logger.warning(f"[order_sizer] OKX 无法获取标记价格 {inst_id}，返回 sz=1")
            return 1.0

        # 3. 合约面值 ctVal（标的数量/张）
        ct_val = self.contract_info.get_contract_size("okx", inst_id)

        # sz = avail_eq * size_pct / (mark_px * ct_val)
        sz = (avail_eq * size_pct) / (mark_px * ct_val)
        sz = max(1.0, math.floor(sz))
        self.logger.info(
            f"[order_sizer] OKX {inst_id}: avail={avail_eq:.2f} USDT, "
            f"mark={mark_px}, ctVal={ct_val}, size_pct={size_pct:.1%} → sz={sz}"
        )
        return sz

    def _parse_okx_balance(self, resp: dict) -> float:
        """解析 OKX 账户余额，取 USDT 可用权益"""
        data = resp.get("data", [])
        if not data:
            raise ValueError(f"OKX 余额响应为空: {resp}")
        for detail in data[0].get("details", []):
            if detail.get("ccy") == "USDT":
                return float(detail.get("availEq") or detail.get("cashBal") or 0)
        raise ValueError("OKX 余额中未找到 USDT")

    async def _get_okx_mark_price(self, loop, inst_id: str) -> Optional[float]:
        try:
            from SDK.okx.PublicData import PublicAPI as OkxPublicAPI
            api = OkxPublicAPI(flag=self._okx_account.flag if hasattr(self._okx_account, 'flag') else "0")
            resp = await loop.run_in_executor(
                None, lambda: api.get_mark_price(instType="SWAP", instId=inst_id)
            )
            data = resp.get("data", [])
            if data:
                return float(data[0].get("markPx", 0))
        except Exception as e:
            self.logger.error(f"[order_sizer] OKX 标记价格查询失败 {inst_id}: {e}")
        return None

    # ------------------------------------------------------------------ #
    #  Binance
    # ------------------------------------------------------------------ #

    async def _compute_binance(
        self, loop, inst_id: str, size_pct: float, mark_px: Optional[float]
    ) -> float:
        if not self._binance_client:
            self.logger.warning("[order_sizer] Binance 未配置 API Key，返回 sz=1")
            return 1.0

        # 1. 查可用余额
        try:
            balances = await loop.run_in_executor(None, self._binance_client.balance)
            avail_usdt = self._parse_binance_balance(balances)
        except Exception as e:
            self.logger.error(f"[order_sizer] Binance 余额查询失败: {e}，返回 sz=1")
            return 1.0

        # 2. 标记价格
        if mark_px is None:
            mark_px = await self._get_binance_mark_price(loop, inst_id)
        if not mark_px or mark_px <= 0:
            self.logger.warning(f"[order_sizer] Binance 无法获取标记价格 {inst_id}，返回 sz=1")
            return 1.0

        # Binance U本位：sz 单位是合约数量（非张），1合约 = 1标的
        # quantity = avail_usdt * size_pct / mark_px
        qty_precision = self.contract_info.get_qty_precision("binance", inst_id)
        raw_qty = (avail_usdt * size_pct) / mark_px
        factor = 10 ** qty_precision
        qty = math.floor(raw_qty * factor) / factor
        qty = max(10 ** (-qty_precision), qty)
        self.logger.info(
            f"[order_sizer] Binance {inst_id}: avail={avail_usdt:.2f} USDT, "
            f"mark={mark_px}, size_pct={size_pct:.1%} → qty={qty}"
        )
        return qty

    def _parse_binance_balance(self, balances: list) -> float:
        for item in balances:
            if item.get("asset") == "USDT":
                return float(item.get("availableBalance") or 0)
        raise ValueError("Binance 余额中未找到 USDT")

    async def get_total_equity(self, exchange: str) -> Optional[float]:
        """查询账户总权益（含未实现盈亏），用于回撤熔断检查"""
        loop = asyncio.get_event_loop()
        if exchange == "okx":
            if not self._okx_account:
                return None
            try:
                resp = await loop.run_in_executor(
                    None, lambda: self._okx_account.get_account_balance(ccy="USDT")
                )
                data = resp.get("data", [])
                if data:
                    return float(data[0].get("totalEq") or 0)
            except Exception as e:
                self.logger.error(f"[order_sizer] OKX 总权益查询失败: {e}")
        elif exchange == "binance":
            if not self._binance_client:
                return None
            try:
                balances = await loop.run_in_executor(None, self._binance_client.balance)
                for item in balances:
                    if item.get("asset") == "USDT":
                        return float(item.get("balance") or 0)
            except Exception as e:
                self.logger.error(f"[order_sizer] Binance 总权益查询失败: {e}")
        return None

    async def _get_binance_mark_price(self, loop, inst_id: str) -> Optional[float]:
        try:
            resp = await loop.run_in_executor(
                None, lambda: self._binance_client.mark_price(symbol=inst_id)
            )
            return float(resp.get("markPrice", 0))
        except Exception as e:
            self.logger.error(f"[order_sizer] Binance 标记价格查询失败 {inst_id}: {e}")
        return None
