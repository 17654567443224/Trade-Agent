import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Send, BarChart2, TrendingUp, ShieldAlert, Loader2, CheckCircle, XCircle } from 'lucide-react'
import { useStore } from '../store/useStore'
import type { QueryState } from '../types'

const API_BASE = 'http://127.0.0.1:8000'

// ── analyst badge ─────────────────────────────────────────────────────────────
const ANALYST_META = {
  chart:       { label: '图表',  icon: BarChart2,   color: '#58a6ff' },
  fundamental: { label: '基本面', icon: TrendingUp,  color: '#3fb950' },
  risk:        { label: '风险',  icon: ShieldAlert,  color: '#d29922' },
} as const

function AnalystBadge({ role, status }: { role: keyof typeof ANALYST_META; status: string }) {
  const { label, icon: Icon, color } = ANALYST_META[role]
  return (
    <span
      className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium"
      style={{ background: `${color}18`, color }}
    >
      <Icon size={11} />
      {label}
      {status === 'loading' && <Loader2 size={10} className="animate-spin ml-0.5" />}
      {status === 'done'    && <CheckCircle size={10} className="ml-0.5" />}
      {status === 'error'   && <XCircle size={10} className="ml-0.5" />}
    </span>
  )
}

// ── single query card ─────────────────────────────────────────────────────────
function QueryCard({ q }: { q: QueryState }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const answerRef = useRef<HTMLDivElement>(null)

  const displayText = q.status === 'done' ? q.finalContent : q.streamingContent
  const isRunning   = q.status === 'running'

  // Auto-scroll the answer box to bottom while streaming
  useEffect(() => {
    if (isRunning && answerRef.current) {
      answerRef.current.scrollTop = answerRef.current.scrollHeight
    }
  }, [displayText, isRunning])

  return (
    <div className="rounded-xl border border-[#30363d] bg-[#161b22] overflow-hidden shrink-0">
      {/* question */}
      <div className="px-4 py-3 flex items-start gap-2">
        <div className="w-6 h-6 rounded-full bg-[#1f6feb] flex items-center justify-center shrink-0 mt-0.5 text-[11px] font-bold text-white">
          Q
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] text-[#e6edf3] leading-snug">{q.question}</p>
          <p className="text-[10px] text-[#8b949e] mt-0.5">{q.instId}</p>
        </div>
      </div>

      {/* analyst progress badges */}
      <div className="px-4 pb-2 flex gap-2 flex-wrap">
        {(['chart', 'fundamental', 'risk'] as const).map((role) => (
          <button
            key={role}
            onClick={() => setExpanded(expanded === role ? null : role)}
            disabled={q.analystStatus[role] === 'pending' || q.analystStatus[role] === 'loading'}
            className="disabled:cursor-default"
          >
            <AnalystBadge role={role} status={q.analystStatus[role]} />
          </button>
        ))}
      </div>

      {/* expandable analyst report */}
      {expanded && q.reports[expanded as keyof typeof q.reports] && (
        <div className="mx-4 mb-3 p-3 rounded-lg bg-[#0d1117] border border-[#30363d] text-[12px] text-[#8b949e] leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
          {q.reports[expanded as keyof typeof q.reports]}
        </div>
      )}

      {/* aggregator answer */}
      {displayText ? (
        <div className="mx-4 mb-4 p-3 rounded-lg bg-[#0d1117] border border-[#21262d] flex flex-col">
          <div className="text-[12px] text-[#8b949e] mb-1.5 flex items-center gap-1 shrink-0">
            <span>综合分析</span>
            {isRunning && <Loader2 size={10} className="animate-spin" />}
          </div>
          {/* scrollable answer body — max 400px, grows naturally when smaller */}
          <div
            ref={answerRef}
            className="overflow-y-auto"
            style={{ maxHeight: '400px' }}
          >
            <p className="text-[13px] text-[#e6edf3] leading-relaxed whitespace-pre-wrap">
              {displayText}
              {isRunning && (
                <span className="inline-block w-1.5 h-3.5 bg-[#58a6ff] ml-0.5 align-middle animate-pulse" />
              )}
            </p>
          </div>
        </div>
      ) : isRunning ? (
        <div className="mx-4 mb-4 p-3 rounded-lg bg-[#0d1117] border border-[#21262d] text-[12px] text-[#8b949e] flex items-center gap-2">
          <Loader2 size={12} className="animate-spin" />
          分析中，请稍候…
        </div>
      ) : null}

      {q.status === 'error' && (
        <div className="mx-4 mb-4 p-3 rounded-lg bg-[#3d1c1c] border border-[#da3633] text-[12px] text-[#ffa198]">
          {q.error}
        </div>
      )}
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────
export function QueryPanel() {
  const queries    = useStore((s) => s.queries)
  const startQuery = useStore((s) => s.startQuery)

  const [input, setInput]   = useState('')
  const [sending, setSending] = useState(false)
  const textareaRef  = useRef<HTMLTextAreaElement>(null)
  const scrollRef    = useRef<HTMLDivElement>(null)
  const isAtBottom   = useRef(true)

  // Track whether user has scrolled away from the bottom
  const onScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    isAtBottom.current = scrollHeight - scrollTop - clientHeight < 60
  }

  // Auto-scroll history list to bottom when new queries arrive or streaming updates
  useEffect(() => {
    if (isAtBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [queries])

  const submit = useCallback(async () => {
    const question = input.trim()
    if (!question || sending) return

    setSending(true)
    // Snap to bottom so the new card is visible
    isAtBottom.current = true

    try {
      const res  = await fetch(`${API_BASE}/api/query`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ question }),
      })
      const json = await res.json()
      if (json.ok) {
        startQuery({
          query_id:      json.query_id,
          question,
          instId:        json.instId ?? '',
          analystStatus: { chart: 'pending', fundamental: 'pending', risk: 'pending' },
          reports:       {},
          streamingContent: '',
          finalContent:  '',
          status:        'running',
          timestamp:     Date.now(),
        })
        setInput('')
      }
    } catch {
      // network error
    } finally {
      setSending(false)
      textareaRef.current?.focus()
    }
  }, [input, sending, startQuery])

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="h-full flex flex-col bg-[#0d1117] rounded-xl border border-[#30363d] overflow-hidden">
      {/* header */}
      <div className="px-4 py-3 border-b border-[#30363d] shrink-0">
        <h2 className="text-[13px] font-semibold text-[#e6edf3]">提问分析</h2>
        <p className="text-[11px] text-[#8b949e] mt-0.5">
          输入问题（如：分析 BTC-USDT-SWAP，给出投资建议）
        </p>
      </div>

      {/* scrollable history */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 min-h-0"
      >
        {queries.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-[13px] text-[#484f58] text-center">
              还没有提问记录<br />
              <span className="text-[11px]">在下方输入框发送问题</span>
            </p>
          </div>
        ) : (
          queries.map((q) => <QueryCard key={q.query_id} q={q} />)
        )}
      </div>

      {/* input */}
      <div className="shrink-0 border-t border-[#30363d] p-3">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="例如：分析 ETH-USDT-SWAP，当前行情适合做多吗？"
            rows={2}
            className="flex-1 min-w-0 resize-none bg-[#161b22] border border-[#30363d] rounded-lg px-3 py-2 text-[13px] text-[#e6edf3] placeholder-[#484f58] focus:outline-none focus:border-[#388bfd] transition-colors leading-snug"
          />
          <button
            onClick={submit}
            disabled={!input.trim() || sending}
            className="shrink-0 w-9 h-9 rounded-lg bg-[#1f6feb] hover:bg-[#388bfd] disabled:bg-[#21262d] disabled:text-[#484f58] text-white flex items-center justify-center transition-colors"
          >
            {sending
              ? <Loader2 size={15} className="animate-spin" />
              : <Send size={15} />
            }
          </button>
        </div>
        <p className="text-[10px] text-[#484f58] mt-1.5">Enter 发送 · Shift+Enter 换行</p>
      </div>
    </div>
  )
}
