// Mirror of backend Pydantic models

export interface TradeSignal {
  exchange: string
  instId: string
  action: 'open' | 'close' | 'hold'
  side: 'buy' | 'sell' | null
  posSide: 'long' | 'short' | null
  size_pct: number
  leverage: number
  order_type: 'market' | 'limit' | null
  px: string | null
  tp_px: string | null
  sl_px: string | null
  reason: string
  sz?: number
  rule_passed?: boolean
  order_result?: Record<string, unknown>
  timestamp?: number
}

export interface AggregatorDecision {
  signals: TradeSignal[]
  market_summary: string
  confidence: number
}

export interface MistakeCorrection {
  error_description: string
  cause: string
  correction_guideline: string
}

export interface SuccessToKeep {
  success_description: string
  why_it_worked: string
  preservation_strategy: string
}

export interface TradingReflection {
  mistakes_and_corrections: MistakeCorrection[]
  successes_to_keep: SuccessToKeep[]
  anti_overfitting_notes: string
}

export interface AnalystReport {
  role: 'chart' | 'fundamental' | 'risk'
  content: string
  timestamp: number
}

export interface Candle {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface KlineData {
  instId: string
  exchange: string
  candles: Candle[]
}

export interface SystemStatus {
  status: 'running' | 'stopped' | 'error'
  message?: string
}

// ── Query types ──────────────────────────────────────────────────────────────

export type QueryAnalystStatus = 'pending' | 'loading' | 'done' | 'error'

export interface QueryState {
  query_id: string
  question: string
  instId: string
  analystStatus: Record<'chart' | 'fundamental' | 'risk', QueryAnalystStatus>
  reports: Partial<Record<'chart' | 'fundamental' | 'risk', string>>
  streamingContent: string   // accumulates tokens while running
  finalContent: string
  status: 'running' | 'done' | 'error'
  error?: string
  timestamp: number
}

export interface KlineBarData {
  instId: string
  exchange: string
  bar: Candle
}

// WebSocket event envelope
export type WsEvent =
  | { type: 'signal'; data: TradeSignal }
  | { type: 'state'; data: { positions: Record<string, unknown>; orders: Record<string, unknown>; symbols: string[] } }
  | { type: 'analyst'; data: AnalystReport }
  | { type: 'decision'; data: AggregatorDecision }
  | { type: 'kline'; data: KlineData }
  | { type: 'kline_bar'; data: KlineBarData }
  | { type: 'reflection'; data: TradingReflection }
  | { type: 'log'; data: { level: string; message: string; timestamp: number } }
  | { type: 'system'; data: SystemStatus }
  | { type: 'snapshot'; data: SnapshotData }
  | { type: 'query_status'; data: { query_id: string; status: string; instId?: string } }
  | { type: 'query_analyst'; data: { query_id: string; role: string; status: string; content?: string } }
  | { type: 'query_token'; data: { query_id: string; token: string } }
  | { type: 'query_done'; data: { query_id: string; content: string } }
  | { type: 'query_error'; data: { query_id: string; error: string } }

export interface SnapshotData {
  status: string
  symbols: string[]
  positions: Record<string, unknown>
  orders: Record<string, unknown>
  latest_decision: AggregatorDecision | null
  analyst_reports: {
    chart: AnalystReport | null
    fundamental: AnalystReport | null
    risk: AnalystReport | null
  }
  recent_signals: TradeSignal[]
  klines?: Record<string, KlineData>
}
