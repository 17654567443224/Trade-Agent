import React from 'react'
import { useStore } from '../store/useStore'

export function PositionsTable() {
  const positions = useStore((s) => s.positions)
  const entries = Object.entries(positions)

  return (
    <div className="flex flex-col bg-[#1c2128] rounded-lg border border-[#30363d] overflow-hidden h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#30363d]"
           style={{ borderTop: '2px solid #3fb950' }}>
        <span className="text-[11px] font-semibold text-[#3fb950]">持仓</span>
        <span className="text-[10px] text-[#484f58]">{entries.length} 个</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-[#484f58] italic">暂无持仓</p>
          </div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-[#1c2128]">
              <tr className="text-[#484f58] border-b border-[#30363d]">
                <th className="text-left px-3 py-1.5 font-medium">合约</th>
                <th className="text-left px-3 py-1.5 font-medium">方向</th>
                <th className="text-right px-3 py-1.5 font-medium">数量</th>
                <th className="text-right px-3 py-1.5 font-medium">开仓价</th>
                <th className="text-right px-3 py-1.5 font-medium">标记价</th>
                <th className="text-right px-3 py-1.5 font-medium">未实现盈亏</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([key, pos]) => {
                const p = pos as Record<string, unknown>
                const instId   = (p.instId || p.symbol || key) as string
                const posSide  = String(p.posSide || '—')
                const size     = p.pos || p.positionAmt || '—'
                const avgPx    = p.avgPx || p.entryPrice || '—'
                const markPx   = p.markPx || p.markPrice || '—'
                const upnl     = p.upl || p.unrealizedProfit
                const upnlNum  = upnl !== undefined ? Number(upnl) : null
                const isLong   = posSide.toLowerCase() === 'long'

                return (
                  <tr key={key} className="border-b border-[#21262d] hover:bg-[#21262d] transition-colors">
                    <td className="px-3 py-2 text-[#c9d1d9] font-medium">{instId}</td>
                    <td className="px-3 py-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        isLong ? 'bg-[#1a3a28] text-[#3fb950]' : 'bg-[#3a1a1a] text-[#f85149]'
                      }`}>
                        {isLong ? '多' : '空'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-[#c9d1d9]">{String(size)}</td>
                    <td className="px-3 py-2 text-right text-[#8b949e]">{String(avgPx)}</td>
                    <td className="px-3 py-2 text-right text-[#8b949e]">{String(markPx)}</td>
                    <td className={`px-3 py-2 text-right font-semibold ${
                      upnlNum === null ? 'text-[#8b949e]'
                      : upnlNum >= 0 ? 'text-[#3fb950]' : 'text-[#f85149]'
                    }`}>
                      {upnlNum === null ? '—' : (upnlNum >= 0 ? '+' : '') + upnlNum.toFixed(4)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
