#!/usr/bin/env python3
"""
Odaily Skill 工具入口
用法: python run.py <tool_name> [json_args]
示例: python run.py get_today_watch '{"limit": 10}'
      python run.py get_crypto_market_analysis '{"focus": "overview"}'
"""
# import os
# import sys

# 把 skill 目录加到 path，使 config/lib/tools 可以直接 import
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOOLS = {
    # M1 今日必关注
    "get_today_watch": ("tools.odaily_news", "get_today_watch"),
    # M2 加密市场分析（含宏观）
    "get_crypto_market_analysis": ("tools.market_trend", "get_crypto_market_analysis"),
    # M3 明日关注
    "get_tomorrow_watch": ("tools.tomorrow_watch", "get_tomorrow_watch"),
    # M4 预测市场异动 + 巨鲸尾盘跟单
    "scan_whale_tail_trades": ("tools.whale_trades", "scan_whale_tail_trades"),
    # M5 API模块化调用
    "get_api_module": ("tools.api_module", "get_api_module"),
    # 向后兼容别名
    "get_odaily_headlines": ("tools.odaily_news", "get_odaily_headlines"),
    "get_market_trend_analysis": ("tools.market_trend", "get_market_trend_analysis"),
}


def main():

    tool_name = "get_today_watch"
    module_path, func_name = TOOLS[tool_name]
    module = __import__(module_path, fromlist=[func_name])
    func = getattr(module, func_name)
    res = func(limit=10)
    print(res)


if __name__ == "__main__":
    main()
