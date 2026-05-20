import React from 'react'
import { useStore } from '../store/useStore'
import type { TradeSignal } from '../types'

const ACTION_LABEL: Record<string, string> = { open: '开仓', close: '平仓', hold: '观望' }
const POS_LABEL:    Record<string, string> = { long: '多', short: '空' }
const ORDER_LABEL:  Record<string, string> = { market: '市价', limit: '限价' }

function signalColor(sig: TradeSignal): string {
  if (sig.action === 'open')  return sig.posSide === 'long' ? '#3fb950' : '#f85149'
  if (sig.action === 'close') return '#e3b341'
  return '#484f58'
}

function SignalCard({ sig }: { sig: TradeSignal }) {
  const color = signalColor(sig)
  const ts = sig.timestamp
    ? new Date(sig.timestamp * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : ''

  return (
    <div
      className="rounded-lg border border-[#30363d] overflow-hidden"
      style={{ background: `${color}0a`, borderLeftColor: color, borderLeftWidth: 3 }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#30363d]"
           style={{ background: `${color}10` }}>
        <span className="text-[11px] font-bold" style={{ color }}>
          {ACTION_LABEL[sig.action]}{sig.posSide ? `·${POS_LABEL[sig.posSide] ?? sig.posSide}` : ''}
        </span>
        <div className="flex items-center gap-2">
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-semibold ${
            sig.rule_passed ? 'bg-[#1a3a28] text-[#3fb950]' : 'bg-[#3a1a1a] text-[#f85149]'
          }`}>
            {sig.rule_passed ? '通过' : '拒绝'}
          </span>
          <span className="text-[10px] text-[#484f58]">{ts}</span>
        </div>
      </div>

      {/* 主体 */}
      <div className="px-3 py-2 flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-[#e6edf3] font-medium">{sig.instId}</span>
          <span className="text-[10px] text-[#484f58] uppercase">{sig.exchange}</span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-[#8b949e]">
          <span>仓位 <span className="text-[#c9d1d9]">{(sig.size_pct * 100).toFixed(0)}%</span></span>
          <span>杠杆 <span className="text-[#c9d1d9]">×{sig.leverage}</span></span>
          {sig.order_type && (
            <span>类型 <span className="text-[#c9d1d9]">{ORDER_LABEL[sig.order_type] ?? sig.order_type}</span></span>
          )}
        </div>
        {sig.reason && (
          <p className="text-[10px] text-[#8b949e] line-clamp-2 leading-relaxed mt-0.5 border-t border-[#30363d] pt-1">
            {sig.reason}
          </p>
        )}
      </div>
    </div>
  )
}

export function SignalFeed() {
  const signals = useStore((s) => s.signals)

  return (
    <div className="flex flex-col bg-[#1c2128] rounded-lg border border-[#30363d] overflow-hidden h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#30363d]"
           style={{ borderTop: '2px solid #58a6ff' }}>
        <span className="text-[11px] font-semibold text-[#58a6ff]">实时信号</span>
        {signals.length > 0 && (
          <span className="text-[10px] text-[#484f58]">{signals.length} 条</span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
        {signals.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-xs text-[#484f58] italic">等待交易信号…</p>
          </div>
        ) : (
          signals.map((sig, i) => <SignalCard key={i} sig={sig} />)
        )}
      </div>
    </div>
  )
}
