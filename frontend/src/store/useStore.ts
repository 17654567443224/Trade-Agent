import { create } from 'zustand'
import type {
  TradeSignal,
  AggregatorDecision,
  AnalystReport,
  TradingReflection,
  KlineData,
  SnapshotData,
  QueryState,
  QueryAnalystStatus,
} from '../types'

interface StoreState {
  // connection
  connected: boolean
  systemStatus: string

  // market
  symbols: string[]
  klines: Record<string, KlineData>   // key = "exchange:instId"
  selectedSymbol: string

  // positions & orders
  positions: Record<string, unknown>
  orders: Record<string, unknown>

  // analyst
  analystReports: {
    chart: AnalystReport | null
    fundamental: AnalystReport | null
    risk: AnalystReport | null
  }

  // aggregator
  latestDecision: AggregatorDecision | null

  // signals
  signals: TradeSignal[]

  // reflections
  reflections: TradingReflection[]

  // queries
  queries: QueryState[]
  startQuery: (q: QueryState) => void
  updateQueryAnalyst: (query_id: string, role: string, status: QueryAnalystStatus, content?: string) => void
  appendQueryToken: (query_id: string, token: string) => void
  finishQuery: (query_id: string, content: string) => void
  errorQuery: (query_id: string, error: string) => void

  // actions
  setConnected: (v: boolean) => void
  setSystemStatus: (s: string) => void
  setSymbols: (s: string[]) => void
  setKlines: (key: string, data: KlineData) => void
  updateKlineBar: (key: string, bar: import('../types').Candle) => void
  setSelectedSymbol: (s: string) => void
  setPositions: (p: Record<string, unknown>) => void
  setOrders: (o: Record<string, unknown>) => void
  setAnalystReport: (r: AnalystReport) => void
  setDecision: (d: AggregatorDecision) => void
  addSignal: (s: TradeSignal) => void
  addReflection: (r: TradingReflection) => void
  applySnapshot: (snap: SnapshotData) => void
}

export const useStore = create<StoreState>((set) => ({
  connected: false,
  systemStatus: 'stopped',
  symbols: [],
  klines: {},
  selectedSymbol: '',
  positions: {},
  orders: {},
  analystReports: { chart: null, fundamental: null, risk: null },
  latestDecision: null,
  signals: [],
  reflections: [],
  queries: [],

  setConnected: (v) => set({ connected: v }),
  setSystemStatus: (s) => set({ systemStatus: s }),
  setSymbols: (symbols) => set((state) => ({
    symbols,
    selectedSymbol: state.selectedSymbol || symbols[0] || '',
  })),
  setKlines: (key, data) => set((state) => ({
    klines: { ...state.klines, [key]: data },
  })),
  updateKlineBar: (key, bar) => set((state) => {
    const existing = state.klines[key]
    if (!existing) {
      // 首个 bar 到达，还没有全量快照 —— 建立条目并激活 selectedSymbol
      const colonIdx = key.indexOf(':')
      const exchange = colonIdx >= 0 ? key.slice(0, colonIdx) : 'unknown'
      const instId   = colonIdx >= 0 ? key.slice(colonIdx + 1) : key
      return {
        klines: { ...state.klines, [key]: { instId, exchange, candles: [bar] } },
        selectedSymbol: state.selectedSymbol || instId,
      }
    }
    const candles = existing.candles
    const last = candles[candles.length - 1]
    // 末位相同时间戳 → 原地更新；否则追加后对整体去重（防止全量快照与实时bar并发产生重复）
    let newCandles
    if (last?.time === bar.time) {
      newCandles = [...candles.slice(0, -1), bar]
    } else {
      const merged = [...candles, bar]
      const seen = new Map(merged.map((c) => [c.time, c]))
      newCandles = Array.from(seen.values()).sort((a, b) => a.time - b.time)
    }
    return { klines: { ...state.klines, [key]: { ...existing, candles: newCandles } } }
  }),
  setSelectedSymbol: (s) => set({ selectedSymbol: s }),
  setPositions: (positions) => set({ positions }),
  setOrders: (orders) => set({ orders }),
  setAnalystReport: (r) => set((state) => ({
    analystReports: { ...state.analystReports, [r.role]: r },
  })),
  setDecision: (d) => set({ latestDecision: d }),
  addSignal: (s) => set((state) => ({
    signals: [s, ...state.signals].slice(0, 200),
  })),
  addReflection: (r) => set((state) => ({
    reflections: [r, ...state.reflections].slice(0, 50),
  })),

  startQuery: (q) => set((state) => {
    const exists = state.queries.some((x) => x.query_id === q.query_id)
    if (exists) {
      // Update instId if the server normalized it (WS query_status confirmation)
      return {
        queries: state.queries.map((x) =>
          x.query_id === q.query_id ? { ...x, instId: q.instId || x.instId } : x
        ),
      }
    }
    return { queries: [q, ...state.queries].slice(0, 50) }
  }),
  updateQueryAnalyst: (query_id, role, status, content) => set((state) => ({
    queries: state.queries.map((q) =>
      q.query_id === query_id
        ? {
            ...q,
            analystStatus: { ...q.analystStatus, [role]: status },
            reports: content !== undefined ? { ...q.reports, [role]: content } : q.reports,
          }
        : q
    ),
  })),
  appendQueryToken: (query_id, token) => set((state) => ({
    queries: state.queries.map((q) =>
      q.query_id === query_id
        ? { ...q, streamingContent: q.streamingContent + token }
        : q
    ),
  })),
  finishQuery: (query_id, content) => set((state) => ({
    queries: state.queries.map((q) =>
      q.query_id === query_id
        ? { ...q, status: 'done', finalContent: content, streamingContent: content }
        : q
    ),
  })),
  errorQuery: (query_id, error) => set((state) => ({
    queries: state.queries.map((q) =>
      q.query_id === query_id ? { ...q, status: 'error', error } : q
    ),
  })),

  applySnapshot: (snap) => set((state) => ({
    systemStatus: snap.status,
    symbols: snap.symbols,
    selectedSymbol: state.selectedSymbol || snap.symbols[0] || '',
    positions: snap.positions,
    orders: snap.orders,
    latestDecision: snap.latest_decision,
    analystReports: snap.analyst_reports,
    signals: snap.recent_signals,
    klines: snap.klines ?? state.klines,
  })),
}))
