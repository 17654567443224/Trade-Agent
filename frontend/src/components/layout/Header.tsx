import React from 'react'
import { useStore } from '../../store/useStore'
import { Wifi, WifiOff, CircleDot } from 'lucide-react'

export function Header() {
  const connected    = useStore((s) => s.connected)
  const systemStatus = useStore((s) => s.systemStatus)
  const symbols      = useStore((s) => s.symbols)

  const statusMap: Record<string, { label: string; cls: string }> = {
    running: { label: '运行中', cls: 'bg-[#1a3a28] text-[#3fb950] border border-[#2ea043]' },
    stopped: { label: '已停止', cls: 'bg-[#21262d] text-[#8b949e] border border-[#30363d]' },
    error:   { label: '异  常', cls: 'bg-[#3a1a1a] text-[#f85149] border border-[#da3633]' },
  }
  const st = statusMap[systemStatus] ?? statusMap.stopped

  return (
    <header className="flex items-center justify-between px-5 py-0 h-11 bg-[#161b22] border-b border-[#30363d] shrink-0 z-20">
      {/* 左：品牌 */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <CircleDot size={16} className="text-[#58a6ff]" />
          <span className="text-[#e6edf3] font-bold text-sm tracking-wide">Trade-Agent</span>
        </div>
        <span className="h-4 w-px bg-[#30363d]" />
        <span className="text-[11px] text-[#8b949e]">AI 量化交易系统</span>
      </div>

      {/* 中：活跃品种滚动条 */}
      <div className="flex items-center gap-1.5 overflow-x-auto max-w-xl scrollbar-hide">
        {symbols.slice(0, 8).map((sym) => (
          <span
            key={sym}
            className="px-2 py-0.5 rounded text-[10px] text-[#8b949e] bg-[#21262d] whitespace-nowrap border border-[#30363d]"
          >
            {sym.replace('-SWAP', '')}
          </span>
        ))}
        {symbols.length > 8 && (
          <span className="text-[10px] text-[#484f58] whitespace-nowrap">+{symbols.length - 8}</span>
        )}
      </div>

      {/* 右：状态 + 连接 */}
      <div className="flex items-center gap-3 shrink-0">
        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${st.cls}`}>
          {st.label}
        </span>
        <div className={`flex items-center gap-1.5 text-[11px] font-medium ${connected ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
          {connected
            ? <Wifi size={13} />
            : <WifiOff size={13} />
          }
          {connected ? '实时' : '断连'}
        </div>
      </div>
    </header>
  )
}
