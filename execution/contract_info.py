import asyncio
import logging
from typing import Dict, Optional

from SDK.okx.PublicData import PublicAPI as OkxPublicAPI
from SDK.binance.um_futures import UMFutures


class ContractInfoCache:
    """
    启动时通过 REST 拉取 OKX / Binance 所有 SWAP 合约面值并缓存。
    提供 get_contract_size(exchange, inst_id) -> float 接口。

    OKX  : PublicAPI.get_instruments(instType='SWAP') → data[].ctVal（每张合约的标的数量）
    Binance: UMFutures.exchange_info() → symbols[].filters 中没有直接的 ctVal，
             Binance U本位合约下单单位是「张」，1张 = quantityPrecision 最小单位，
             合约面值统一视作 1（即下单数量直接用 USDT / 标记价格计算）。
    """

    def __init__(self, okx_flag: str = "0", logger=None):
        """
        okx_flag: "0" = 实盘, "1" = 模拟盘
        """
        self.logger = logger or logging.getLogger(__name__)
        self.okx_flag = okx_flag
        # {exchange: {instId: contract_size}}
        self._cache: Dict[str, Dict[str, float]] = {"okx": {}, "binance": {}}
        # Binance 额外缓存每个 symbol 的最小下单精度
        self._binance_qty_precision: Dict[str, int] = {}

    async def load(self, load_okx: bool = True, load_binance: bool = True) -> None:
        """并发拉取两个交易所的合约信息"""
        tasks = []
        if load_okx:
            tasks.append(self._load_okx())
        if load_binance:
            tasks.append(self._load_binance())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _load_okx(self) -> None:
        loop = asyncio.get_event_loop()
        try:
            api = OkxPublicAPI(flag=self.okx_flag)
            resp = await loop.run_in_executor(
                None, lambda: api.get_instruments(instType="SWAP")
            )
            if resp.get("code") != "0":
                self.logger.error(f"[contract_info] OKX instruments 拉取失败: {resp}")
                return
            for item in resp.get("data", []):
                inst_id = item.get("instId", "")
                ct_val = item.get("ctVal")
                if inst_id and ct_val:
                    try:
                        self._cache["okx"][inst_id] = float(ct_val)
                    except ValueError:
                        pass
            self.logger.info(f"[contract_info] OKX 合约面值已缓存，共 {len(self._cache['okx'])} 个品种")
        except Exception as e:
            self.logger.error(f"[contract_info] OKX 拉取异常: {e}")

    async def _load_binance(self) -> None:
        loop = asyncio.get_event_loop()
        try:
            client = UMFutures()
            resp = await loop.run_in_executor(None, client.exchange_info)
            for sym in resp.get("symbols", []):
                symbol = sym.get("symbol", "")
                # Binance U本位合约 1张 = 1 USDT 计价单位，ctVal 视为 1
                self._cache["binance"][symbol] = 1.0
                qty_precision = sym.get("quantityPrecision", 0)
                self._binance_qty_precision[symbol] = qty_precision
            self.logger.info(f"[contract_info] Binance 合约信息已缓存，共 {len(self._cache['binance'])} 个品种")
        except Exception as e:
            self.logger.error(f"[contract_info] Binance 拉取异常: {e}")

    def get_contract_size(self, exchange: str, inst_id: str) -> float:
        """
        返回合约面值（每张合约对应的标的数量）。
        OKX  : ctVal，例如 BTC-USDT-SWAP = 0.01（每张 = 0.01 BTC）
        Binance: 固定返回 1.0（下单单位已是 USDT/标的数量，无需额外换算）
        未找到时返回 1.0 并记录警告。
        """
        val = self._cache.get(exchange, {}).get(inst_id)
        if val is None:
            self.logger.warning(f"[contract_info] 未找到合约面值: {exchange} {inst_id}，使用默认值 1.0")
            return 1.0
        return val

    def get_qty_precision(self, exchange: str, inst_id: str) -> int:
        """返回 Binance 品种的数量精度（小数位数），其他交易所返回 0"""
        if exchange == "binance":
            return self._binance_qty_precision.get(inst_id, 0)
        return 0
