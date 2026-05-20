import React from 'react'
import { RadialBarChart, RadialBar, PolarAngleAxis } from 'recharts'
import { useStore } from '../store/useStore'

const ACTION_LABEL: Record<string, string> = { open: '开仓', close: '平仓', hold: '观望' }
const POS_LABEL:    Record<string, string> = { long: '多', short: '空' }
const ACTION_COLOR: Record<string, string> = {
  'open-long':  '#3fb950',
  'open-short': '#f85149',
  'close':      '#e3b341',
  'hold':       '#484f58',
}

export function AggregatorPanel() {
  const decision = useStore((s) => s.latestDecision)

  const confidence = decision?.confidence ?? 0
  const pct   = Math.round(confidence * 100)
  const color = pct >= 70 ? '#3fb950' : pct >= 40 ? '#e3b341' : '#f85149'

  return (
    <div className="flex flex-col bg-[#1c2128] rounded-lg border border-[#30363d] overflow-hidden h-full">
      {/* 标题 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#30363d]"
           style={{ borderTop: '2px solid #bc8cff' }}>
        <span className="text-[11px] font-semibold text-[#bc8cff]">综合决策</span>
        {decision && (
          <span className="text-[10px] text-[#484f58]">
            置信度 <span style={{ color }} className="font-bold">{pct}%</span>
          </span>
        )}
      </div>

      <div className="flex flex-1 gap-3 p-3 min-h-0 overflow-hidden">
        {/* 置信度圆弧仪表 */}
        <div className="flex flex-col items-center justify-center shrink-0 w-20">
          <div className="relative">
            <RadialBarChart width={80} height={80} cx={40} cy={40} innerRadius={28} outerRadius={38}
              barSize={10} data={[{ value: pct, fill: color }]}
              startAngle={90} endAngle={-270}>
              <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
              <RadialBar dataKey="value" cornerRadius={5} background={{ fill: '#21262d' }} />
            </RadialBarChart>
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <span className="text-sm font-bold" style={{ color }}>{pct}%</span>
            </div>
          </div>
        </div>

        {/* 摘要 + 信号列表 */}
        <div className="flex flex-col gap-2 flex-1 overflow-y-auto min-h-0">
          {decision ? (
            <>
              <p className="text-[11px] text-[#8b949e] leading-relaxed line-clamp-3">
                {decision.market_summary}
              </p>
              <div className="flex flex-col gap-1">
                {decision.signals.map((sig, i) => {
                  const colorKey = sig.action === 'open'
                    ? `open-${sig.posSide}`
                    : sig.action
                  const c = ACTION_COLOR[colorKey] ?? '#8b949e'
                  return (
                    <div key={i}
                      className="flex items-center gap-2 text-[11px] rounded px-2 py-1 border border-[#30363d]"
                      style={{ background: `${c}10` }}>
                      <span className="font-bold w-14 shrink-0" style={{ color: c }}>
                        {ACTION_LABEL[sig.action]}{sig.posSide ? `·${POS_LABEL[sig.posSide] ?? sig.posSide}` : ''}
                      </span>
                      <span
                        className="text-[#c9d1d9] flex-1 truncate"
                        title={sig.instId}
                      >
                        {sig.instId.replace(/-SWAP$|-PERP$/, '').replace('USDT', '/USDT')}
                      </span>
                      <span className="text-[#58a6ff] shrink-0 text-[10px]">
                        {(sig.size_pct * 100).toFixed(0)}% ×{sig.leverage}
                      </span>
                    </div>
                  )
                })}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-xs text-[#484f58] italic">等待决策中…</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
