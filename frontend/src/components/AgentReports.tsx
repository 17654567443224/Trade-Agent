import React from 'react'
import { useStore } from '../store/useStore'

const ROLES = [
  { key: 'fundamental' as const, label: '基本面分析师', color: '#58a6ff', bg: 'rgba(88,166,255,0.08)' },
  { key: 'chart'       as const, label: '图表分析师',   color: '#e3b341', bg: 'rgba(227,179,65,0.08)'  },
  { key: 'risk'        as const, label: '风险分析师',   color: '#f85149', bg: 'rgba(248,81,73,0.08)'   },
]

function timeAgo(ts: number | undefined): string {
  if (!ts) return ''
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60)   return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  return `${Math.floor(diff / 3600)}小时前`
}

export function AgentReports() {
  const reports = useStore((s) => s.analystReports)

  return (
    <div className="grid grid-cols-3 gap-3 h-full">
      {ROLES.map(({ key, label, color, bg }) => {
        const report = reports[key]
        return (
          <div
            key={key}
            className="flex flex-col rounded-lg border border-[#30363d] overflow-hidden h-full"
            style={{ background: '#1c2128' }}
          >
            {/* 顶部色条 + 标题 */}
            <div
              className="flex items-center justify-between px-3 py-2 border-b border-[#30363d]"
              style={{ background: bg, borderTop: `2px solid ${color}` }}
            >
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
                <span className="text-[11px] font-semibold" style={{ color }}>{label}</span>
              </div>
              {report && (
                <span className="text-[10px] text-[#484f58]">{timeAgo(report.timestamp)}</span>
              )}
            </div>

            {/* 内容 */}
            <div className="flex-1 overflow-y-auto p-3">
              {report ? (
                <p className="text-[11px] text-[#c9d1d9] leading-relaxed whitespace-pre-wrap">
                  {report.content}
                </p>
              ) : (
                <div className="h-full flex items-center justify-center">
                  <p className="text-xs text-[#484f58] italic">等待报告中…</p>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
