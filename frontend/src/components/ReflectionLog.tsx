import React, { useState } from 'react'
import { useStore } from '../store/useStore'
import type { TradingReflection } from '../types'
import { ChevronDown, ChevronUp } from 'lucide-react'

function ReflectionCard({ r, idx }: { r: TradingReflection; idx: number }) {
  const [open, setOpen] = useState(idx === 0)
  const hasErrors    = r.mistakes_and_corrections.length > 0
  const hasSuccesses = r.successes_to_keep.length > 0

  return (
    <div className="rounded-lg border border-[#30363d] overflow-hidden bg-[#21262d]">
      {/* 折叠头 */}
      <button
        className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-[#2d333b] transition-colors"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-[#bc8cff]">反思记录 #{idx + 1}</span>
          <div className="flex gap-1">
            {hasErrors && (
              <span className="px-1.5 py-0.5 rounded-full text-[9px] bg-[#3a1a1a] text-[#f85149]">
                {r.mistakes_and_corrections.length} 项错误
              </span>
            )}
            {hasSuccesses && (
              <span className="px-1.5 py-0.5 rounded-full text-[9px] bg-[#1a3a28] text-[#3fb950]">
                {r.successes_to_keep.length} 项成功
              </span>
            )}
          </div>
        </div>
        {open ? <ChevronUp size={14} className="text-[#484f58]" /> : <ChevronDown size={14} className="text-[#484f58]" />}
      </button>

      {open && (
        <div className="border-t border-[#30363d] px-3 py-3 flex flex-col gap-3">
          {/* 错误分析 */}
          {r.mistakes_and_corrections.map((m, i) => (
            <div key={i} className="rounded-lg border border-[#f8514930] bg-[#f8514908] p-2.5 flex flex-col gap-1">
              <p className="text-[11px] text-[#f85149] font-semibold">{m.error_description}</p>
              <p className="text-[10px] text-[#8b949e]"><span className="text-[#484f58]">根因：</span>{m.cause}</p>
              <p className="text-[10px] text-[#3fb950]"><span className="text-[#484f58]">改进：</span>{m.correction_guideline}</p>
            </div>
          ))}

          {/* 成功经验 */}
          {r.successes_to_keep.map((s, i) => (
            <div key={i} className="rounded-lg border border-[#3fb95030] bg-[#3fb95008] p-2.5 flex flex-col gap-1">
              <p className="text-[11px] text-[#3fb950] font-semibold">{s.success_description}</p>
              <p className="text-[10px] text-[#8b949e]"><span className="text-[#484f58]">有效原因：</span>{s.why_it_worked}</p>
            </div>
          ))}

          {/* 防过拟合 */}
          {r.anti_overfitting_notes && (
            <div className="rounded-lg border border-[#e3b34130] bg-[#e3b34108] p-2.5 flex flex-col gap-1">
              <p className="text-[11px] text-[#e3b341] font-semibold">防过拟合提示</p>
              <p className="text-[10px] text-[#8b949e] leading-relaxed">{r.anti_overfitting_notes}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ReflectionLog() {
  const reflections = useStore((s) => s.reflections)

  return (
    <div className="flex flex-col bg-[#1c2128] rounded-lg border border-[#30363d] overflow-hidden h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#30363d]"
           style={{ borderTop: '2px solid #bc8cff' }}>
        <span className="text-[11px] font-semibold text-[#bc8cff]">反思日志</span>
        <span className="text-[10px] text-[#484f58]">{reflections.length} 条</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {reflections.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-xs text-[#484f58] italic">每累计 5 次实际交易轮次后触发反思…</p>
          </div>
        ) : (
          reflections.map((r, i) => <ReflectionCard key={i} r={r} idx={i} />)
        )}
      </div>
    </div>
  )
}
