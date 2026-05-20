class FallbackStrategy:
    """LLM 不可用时的兜底策略"""
    def __init__(self, position):
        self.position = position

    def on_kline(self, data: dict):
        """
        data:dict
            {
                symbol:[]
            }
        开/平
        """
        if not data:
            return
        sym, kline = next(iter(data.items()))
        
















