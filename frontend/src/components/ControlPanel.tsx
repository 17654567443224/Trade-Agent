import React, { useState } from 'react'
import { Play, Square, Zap, RefreshCw } from 'lucide-react'
import { useStore } from '../store/useStore'

export function ControlPanel() {
  const systemStatus = useStore((s) => s.systemStatus)
  const [loading, setLoading] = useState<string | null>(null)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)

  const post = async (path: string, body?: unknown) => {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    return res.json()
  }

  const handleAction = async (action: string) => {
    setLoading(action)
    setMessage(null)
    try {
      let data: { ok: boolean; message: string }
      if (action === 'trigger') {
        data = await post('/api/trigger')
      } else {
        data = await post('/api/control', { action })
      }
      setMessage({ text: data.message || (data.ok ? '操作成功' : '操作失败'), ok: data.ok })
    } catch {
      setMessage({ text: '请求失败', ok: false })
    } finally {
      setLoading(null)
    }
  }

  const isRunning = systemStatus === 'running'

  return (
    <div className="flex flex-col bg-[#1c2128] rounded-lg border border-[#30363d] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#30363d]">
        <span className="text-[11px] font-semibold text-[#8b949e]">策略控制</span>
        {/* 状态指示灯 */}
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-[#3fb950] animate-pulse' : 'bg-[#484f58]'}`} />
          <span className={`text-[10px] font-medium ${isRunning ? 'text-[#3fb950]' : 'text-[#484f58]'}`}>
            {isRunning ? '运行中' : '已停止'}
          </span>
        </div>
      </div>

      <div className="p-3 flex flex-col gap-2">
        {/* 启动/停止 */}
        <button
          onClick={() => handleAction(isRunning ? 'stop' : 'start')}
          disabled={loading !== null}
          className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all duration-150 disabled:opacity-40 ${
            isRunning
              ? 'bg-[#3a1a1a] text-[#f85149] border border-[#da3633] hover:bg-[#4a2020]'
              : 'bg-[#1a3a28] text-[#3fb950] border border-[#2ea043] hover:bg-[#1f4a30]'
          }`}
        >
          {loading === 'start' || loading === 'stop'
            ? <RefreshCw size={13} className="animate-spin" />
            : isRunning ? <Square size={13} /> : <Play size={13} />
          }
          {loading === 'start' || loading === 'stop'
            ? '处理中…'
            : isRunning ? '停止工作流' : '启动工作流'}
        </button>

        {/* 立即触发 */}
        <button
          onClick={() => handleAction('trigger')}
          disabled={loading !== null || !isRunning}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold bg-[#21262d] text-[#e3b341] border border-[#30363d] hover:bg-[#2d333b] hover:border-[#e3b341] transition-all duration-150 disabled:opacity-40"
        >
          {loading === 'trigger'
            ? <RefreshCw size={13} className="animate-spin" />
            : <Zap size={13} />
          }
          立即触发分析
        </button>

        {/* 反馈消息 */}
        {message && (
          <p className={`text-[10px] text-center px-2 py-1 rounded ${
            message.ok ? 'text-[#3fb950] bg-[#1a3a28]' : 'text-[#f85149] bg-[#3a1a1a]'
          }`}>
            {message.text}
          </p>
        )}
      </div>
    </div>
  )
}
