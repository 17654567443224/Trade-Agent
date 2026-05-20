import pandas as pd

from utils.logger_engine import LoggerEngine


class Fundamental:
    def __init__(self, source, logger_engine:LoggerEngine):
        """
        source:
                "okx", "binance"

        """
        self.logger = logger_engine.get_logger("data.Fundamental")
        self.source = source
        if self.source == "okx":
            from SDK.okx.PublicData import PublicAPI as Public
            from SDK.okx.TradingData import TradingDataAPI as TradingData
            from SDK.okx.utils import deal_message
            self.deal_message = deal_message
            self.public = Public(logger=self.logger)
            self.trading_data = TradingData(logger=self.logger)

    def get_data(self, symbols:list):
        fd_data = None
        if self.source == "okx":
            fd_data = self._okx_fundamental(symbols)
        return fd_data

    def _data_preprocessing(self, df: pd.DataFrame):
        df = df.copy()
        # 去重
        if 'symbol' in df.columns:
            df = df.drop_duplicates(subset=['symbol'], keep='last')
        else:
            df = df.drop_duplicates()
        # 空值处理
        df = df.dropna(how='all')
        return df.reset_index(drop=True)

    def _okx_fundamental(self, symbols):
        try:
            # 获取合约当前资金费率
            funding_rate = self.deal_message(self.public.get_funding_rate(instId="ANY"))
            funding_rate = [{
                'symbol': fd.pop('instId'),
                'fundingRate': fd.pop('fundingRate'),
                'fundingTime': int(int(fd.pop('fundingTime')) / 1000),
                'interestRate': fd.pop('interestRate'),
                'premium': fd.pop('premium')
            } for fd in funding_rate if fd['instId'] in symbols]
            # 获取持仓总量
            open_interest = self.deal_message(self.public.get_open_interest("SWAP"))
            open_interest = [{
                'symbol': oi.pop('instId'),
                'open_interest_usd': int(float(oi.pop('oiUsd')))
            } for oi in open_interest if oi['instId'] in symbols]
            return {
                'okx_fundamental': {
                    'funding_rate': funding_rate,
                    'open_interest': open_interest
                }
            }
        except Exception as e:
            self.logger.error(e)
# lg = LoggerEngine()
# fd = Fundamental(source="okx", logger_engine=lg)
# res = fd._okx_fundamental(symbols=['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])
# print(res)

