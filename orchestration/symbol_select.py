import numpy as np


def _compute_metrics(kline_data: dict) -> dict[str, dict[str, float]]:
    """
    计算每个symbol的三项涨跌幅指标。
    返回: {symbol: {"latest": float, "overall": float, "avg": float}}
    """
    metrics = {}
    for symbol, data in kline_data.items():
        if len(data) < 2:
            continue

        # 最新K线涨跌幅
        latest = (data[-1][4] - data[-2][4]) / data[-2][4] * 100

        # 整体涨跌幅
        overall = (data[-1][4] - data[0][4]) / data[0][4] * 100

        # 平均每根K线涨跌幅
        pcts = [
            (data[i][4] - data[i - 1][4]) / data[i - 1][4] * 100
            for i in range(1, len(data))
        ]
        avg = float(np.mean(pcts))

        metrics[symbol] = {"latest": latest, "overall": overall, "avg": avg}

    return metrics


def _select_by_metric(
    metrics: dict[str, dict[str, float]],
    metric_key: str,
    n: int,
) -> set[str]:
    """
    按某项指标排序后，取涨跌幅最高n个、居中n个、最低n个symbol，返回并集。
    """
    symbols = sorted(metrics.keys(), key=lambda s: metrics[s][metric_key])
    total = len(symbols)

    # 不足3n时直接返回全部
    if total < 3 * n:
        return set(symbols)

    top = set(symbols[-n:])
    bottom = set(symbols[:n])

    mid_start = (total - n) // 2
    middle = set(symbols[mid_start: mid_start + n])

    return top | middle | bottom


def _compute_avg_volume(kline_data: dict) -> dict[str, float]:
    """
    计算每个symbol全段K线的平均成交量（K线第6列，index=5）。
    返回: {symbol: avg_volume}
    """
    avg_vol = {}
    for symbol, data in kline_data.items():
        if not data:
            continue
        avg_vol[symbol] = float(np.mean([bar[5] for bar in data]))
    return avg_vol


def _filter_by_volume(
    selected: set[str],
    avg_vol: dict[str, float],
    all_kline: dict,
) -> set[str]:
    """
    对已选品种按平均成交量做中位数过滤：
    - 低于中位数的品种被剔除
    - 从未选中的品种中，按成交量从高到低补入等量品种
    返回过滤后的品种集合。
    """
    # 只保留有成交量数据的品种
    selected_with_vol = {s: avg_vol[s] for s in selected if s in avg_vol}
    if not selected_with_vol:
        return selected

    median_vol = float(np.median(list(selected_with_vol.values())))

    passed = {s for s, v in selected_with_vol.items() if v >= median_vol}
    removed_count = len(selected) - len(passed)

    if removed_count <= 0:
        return passed

    # 从未选中的品种里按成交量降序补入
    unselected_sorted = sorted(
        [s for s in avg_vol if s not in selected and s in all_kline],
        key=lambda s: avg_vol[s],
        reverse=True,
    )
    supplements = set(unselected_sorted[:removed_count])

    return passed | supplements


def get_data(kline_data: dict, n: int = 3) -> dict:
    """
    从所有K线数据中筛选交易对：
    1. 对三项价格指标（最新K线、整体、平均每根涨跌幅）各自取最高/居中/最低各n个，取并集
    2. 对并集中的品种按平均成交量求中位数，剔除低于中位数的低流动性品种
    3. 从未选中品种中按成交量从高到低补入等量品种，保持总数不变
    - 若总品种数 < 3n，跳过价格筛选直接进行成交量过滤
    返回: {symbol: kline_data}
    """
    metrics = _compute_metrics(kline_data)
    total = len(metrics)

    if total < 3 * n:
        selected = set(metrics.keys())
    else:
        selected = set()
        for key in ("latest", "overall", "avg"):
            selected |= _select_by_metric(metrics, key, n)

    avg_vol = _compute_avg_volume(kline_data)
    final = _filter_by_volume(selected, avg_vol, kline_data)

    return {s: kline_data[s] for s in final if s in kline_data}
