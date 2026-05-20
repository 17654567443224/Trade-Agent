import React from 'react'
import { useStore } from '../store/useStore'

export function OrdersTable() {
  const orders  = useStore((s) => s.orders)
  const entries = Object.entries(orders)

  return (
    <div className="flex flex-col bg-[#1c2128] rounded-lg border border-[#30363d] overflow-hidden h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#30363d]"
           style={{ borderTop: '2px solid #e3b341' }}>
        <span className="text-[11px] font-semibold text-[#e3b341]">委托订单</span>
        <span className="text-[10px] text-[#484f58]">{entries.length} 笔</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-[#484f58] italic">暂无委托订单</p>
          </div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-[#1c2128]">
              <tr className="text-[#484f58] border-b border-[#30363d]">
                <th className="text-left px-3 py-1.5 font-medium">订单号</th>
                <th className="text-left px-3 py-1.5 font-medium">合约</th>
                <th className="text-left px-3 py-1.5 font-medium">方向</th>
                <th className="text-right px-3 py-1.5 font-medium">数量</th>
                <th className="text-right px-3 py-1.5 font-medium">委托价</th>
                <th className="text-left px-3 py-1.5 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([key, ord]) => {
                const o      = ord as Record<string, unknown>
                const isBuy  = String(o.side) === 'buy'
                const state  = String(o.state || o.status || '—')
                const stateColor =
                  state === 'live'      ? '#e3b341' :
                  state === 'filled'    ? '#3fb950' :
                  state === 'canceled'  ? '#484f58' : '#8b949e'

                return (
                  <tr key={key} className="border-b border-[#21262d] hover:bg-[#21262d] transition-colors">
                    <td className="px-3 py-2 text-[#484f58] font-mono text-[10px]">
                      …{String(o.ordId || key).slice(-8)}
                    </td>
                    <td className="px-3 py-2 text-[#c9d1d9] font-medium">
                      {String(o.instId || o.symbol || '—')}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        isBuy ? 'bg-[#1a3a28] text-[#3fb950]' : 'bg-[#3a1a1a] text-[#f85149]'
                      }`}>
                        {isBuy ? '买入' : '卖出'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-[#c9d1d9]">
                      {String(o.sz || o.origQty || '—')}
                    </td>
                    <td className="px-3 py-2 text-right text-[#8b949e]">
                      {String(o.px || o.price || '—')}
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-[10px] font-medium" style={{ color: stateColor }}>
                        {state}
                      </span>
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
