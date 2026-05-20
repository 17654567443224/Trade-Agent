import React from 'react'
import { BarChart2, Activity, Layers, BookOpen, Settings, TrendingUp, MessageSquare } from 'lucide-react'

interface SidebarProps {
  active: string
  onSelect: (v: string) => void
}

const NAV = [
  { id: 'dashboard',   icon: BarChart2,     label: '总览' },
  { id: 'query',       icon: MessageSquare, label: '提问' },
  { id: 'signals',     icon: Activity,      label: '信号' },
  { id: 'positions',   icon: Layers,        label: '持仓' },
  { id: 'reflections', icon: BookOpen,      label: '反思' },
  { id: 'control',     icon: Settings,      label: '控制' },
]

export function Sidebar({ active, onSelect }: SidebarProps) {
  return (
    <aside className="w-20 flex flex-col items-center py-4 gap-1 bg-[#161b22] border-r border-[#30363d] shrink-0">
      {/* logo */}
      <div className="mb-5 flex flex-col items-center gap-1">
        <TrendingUp className="text-[#58a6ff]" size={22} />
        <span className="text-[9px] text-[#58a6ff] tracking-widest font-semibold uppercase">TA</span>
      </div>

      {NAV.map(({ id, icon: Icon, label }) => (
        <button
          key={id}
          onClick={() => onSelect(id)}
          className={`w-16 py-2.5 rounded-lg flex flex-col items-center gap-1 transition-all duration-150 ${
            active === id
              ? 'bg-[#1f6feb] text-white shadow-[0_0_12px_rgba(31,111,235,0.4)]'
              : 'text-[#8b949e] hover:bg-[#21262d] hover:text-[#e6edf3]'
          }`}
        >
          <Icon size={17} />
          <span className="text-[10px] font-medium">{label}</span>
        </button>
      ))}
    </aside>
  )
}
