from SDK.binance.api import API


class UMFutures(API):
    def __init__(self, key=None, secret=None, **kwargs):
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://fapi.binance.com"
        super().__init__(key, secret, **kwargs)

    # MARKETS
    from SDK.binance.um_futures.market import ping
    from SDK.binance.um_futures.market import time
    from SDK.binance.um_futures.market import exchange_info
    from SDK.binance.um_futures.market import depth
    from SDK.binance.um_futures.market import trades
    from SDK.binance.um_futures.market import historical_trades
    from SDK.binance.um_futures.market import agg_trades
    from SDK.binance.um_futures.market import klines
    from SDK.binance.um_futures.market import continuous_klines
    from SDK.binance.um_futures.market import index_price_klines
    from SDK.binance.um_futures.market import mark_price_klines
    from SDK.binance.um_futures.market import mark_price
    from SDK.binance.um_futures.market import funding_rate
    from SDK.binance.um_futures.market import funding_info
    from SDK.binance.um_futures.market import ticker_24hr_price_change
    from SDK.binance.um_futures.market import ticker_price
    from SDK.binance.um_futures.market import book_ticker
    from SDK.binance.um_futures.market import quarterly_contract_settlement_price
    from SDK.binance.um_futures.market import open_interest
    from SDK.binance.um_futures.market import open_interest_hist
    from SDK.binance.um_futures.market import top_long_short_position_ratio
    from SDK.binance.um_futures.market import long_short_account_ratio
    from SDK.binance.um_futures.market import top_long_short_account_ratio
    from SDK.binance.um_futures.market import taker_long_short_ratio
    from SDK.binance.um_futures.market import blvt_kline
    from SDK.binance.um_futures.market import index_info
    from SDK.binance.um_futures.market import asset_Index
    from SDK.binance.um_futures.market import index_price_constituents

    # ACCSDKOUNT(including orders and trades)
    from SDK.binance.um_futures.account import change_position_mode
    from SDK.binance.um_futures.account import get_position_mode
    from SDK.binance.um_futures.account import change_multi_asset_mode
    from SDK.binance.um_futures.account import get_multi_asset_mode
    from SDK.binance.um_futures.account import new_order
    from SDK.binance.um_futures.account import new_order_test
    from SDK.binance.um_futures.account import modify_order
    from SDK.binance.um_futures.account import new_batch_order
    from SDK.binance.um_futures.account import query_order
    from SDK.binance.um_futures.account import cancel_order
    from SDK.binance.um_futures.account import cancel_open_orders
    from SDK.binance.um_futures.account import cancel_batch_order
    from SDK.binance.um_futures.account import countdown_cancel_order
    from SDK.binance.um_futures.account import get_open_orders
    from SDK.binance.um_futures.account import get_orders
    from SDK.binance.um_futures.account import get_all_orders
    from SDK.binance.um_futures.account import balance
    from SDK.binance.um_futures.account import account
    from SDK.binance.um_futures.account import change_leverage
    from SDK.binance.um_futures.account import change_margin_type
    from SDK.binance.um_futures.account import modify_isolated_position_margin
    from SDK.binance.um_futures.account import get_position_margin_history
    from SDK.binance.um_futures.account import get_position_risk
    from SDK.binance.um_futures.account import get_account_trades
    from SDK.binance.um_futures.account import get_income_history
    from SDK.binance.um_futures.account import leverage_brackets
    from SDK.binance.um_futures.account import adl_quantile
    from SDK.binance.um_futures.account import force_orders
    from SDK.binance.um_futures.account import api_trading_status
    from SDK.binance.um_futures.account import commission_rate
    from SDK.binance.um_futures.account import futures_account_configuration
    from SDK.binance.um_futures.account import symbol_configuration
    from SDK.binance.um_futures.account import query_user_rate_limit
    from SDK.binance.um_futures.account import download_transactions_asyn
    from SDK.binance.um_futures.account import aysnc_download_info
    from SDK.binance.um_futures.account import download_order_asyn
    from SDK.binance.um_futures.account import async_download_order_id
    from SDK.binance.um_futures.account import download_trade_asyn
    from SDK.binance.um_futures.account import async_download_trade_id
    from SDK.binance.um_futures.account import toggle_bnb_burn
    from SDK.binance.um_futures.account import get_bnb_burn

    # CONSDKVERT
    from SDK.binance.um_futures.convert import list_all_convert_pairs
    from SDK.binance.um_futures.convert import send_quote_request
    from SDK.binance.um_futures.convert import accept_offered_quote
    from SDK.binance.um_futures.convert import order_status

    # STRSDKEAMS
    from SDK.binance.um_futures.data_stream import new_listen_key
    from SDK.binance.um_futures.data_stream import renew_listen_key
    from SDK.binance.um_futures.data_stream import close_listen_key
