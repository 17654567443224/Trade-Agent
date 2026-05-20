import React, { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { Header } from './components/layout/Header'
import { Sidebar } from './components/layout/Sidebar'
import { KlineChart } from './components/KlineChart'
import { AgentReports } from './components/AgentReports'
import { AggregatorPanel } from './components/AggregatorPanel'
import { PositionsTable } from './components/PositionsTable'
import { OrdersTable } from './components/OrdersTable'
import { SignalFeed } from './components/SignalFeed'
import { ControlPanel } from './components/ControlPanel'
import { ReflectionLog } from './components/ReflectionLog'
import { QueryPanel } from './components/QueryPanel'

export default function App() {
  useWebSocket()
  const [page, setPage] = useState('dashboard')

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0d1117]">
      <Header />
      <div className="flex flex-1 min-h-0">
        <Sidebar active={page} onSelect={setPage} />
        <main className="flex-1 min-w-0 overflow-hidden">
          {page === 'dashboard'   && <DashboardPage />}
          {page === 'query'       && <QueryPage />}
          {page === 'signals'     && <SignalsPage />}
          {page === 'positions'   && <PositionsPage />}
          {page === 'reflections' && <ReflectionsPage />}
          {page === 'control'     && <ControlPage />}
        </main>
      </div>
    </div>
  )
}

/* ── Dashboard ──────────────────────────────────────────────────────────── */
function DashboardPage() {
  return (
    <div className="h-full flex flex-col p-3 gap-3">
      {/* 上半：K线 + 信号流 */}
      <div className="flex gap-3 min-h-0" style={{ flex: '3' }}>
        {/* K线图，占大部分宽度 */}
        <div className="flex-1 min-w-0">
          <KlineChart />
        </div>
        {/* 信号流 + 控制面板，右侧固定宽度 */}
        <div className="flex flex-col gap-3 w-72 shrink-0">
          <div className="flex-1 min-h-0">
            <SignalFeed />
          </div>
          <div className="shrink-0">
            <ControlPanel />
          </div>
        </div>
      </div>

      {/* 中间：三个分析师报告 */}
      <div style={{ flex: '2' }} className="min-h-0">
        <AgentReports />
      </div>

      {/* 下方：综合决策 + 持仓 + 订单 */}
      <div className="flex gap-3 shrink-0" style={{ height: '180px' }}>
        <div className="w-72 shrink-0">
          <AggregatorPanel />
        </div>
        <div className="flex-1 min-w-0">
          <PositionsTable />
        </div>
        <div className="flex-1 min-w-0">
          <OrdersTable />
        </div>
      </div>
    </div>
  )
}

/* ── Query ──────────────────────────────────────────────────────────────── */
function QueryPage() {
  return (
    <div className="h-full p-3">
      <QueryPanel />
    </div>
  )
}

/* ── Signals ────────────────────────────────────────────────────────────── */
function SignalsPage() {
  return (
    <div className="h-full p-3 flex gap-3">
      <div className="flex-1 min-w-0">
        <SignalFeed />
      </div>
      <div className="w-64 shrink-0 flex flex-col gap-3">
        <ControlPanel />
        <AggregatorPanel />
      </div>
    </div>
  )
}

/* ── Positions ──────────────────────────────────────────────────────────── */
function PositionsPage() {
  return (
    <div className="h-full p-3 flex flex-col gap-3">
      <div className="flex-1 min-h-0">
        <PositionsTable />
      </div>
      <div className="flex-1 min-h-0">
        <OrdersTable />
      </div>
    </div>
  )
}

/* ── Reflections ────────────────────────────────────────────────────────── */
function ReflectionsPage() {
  return (
    <div className="h-full p-3">
      <ReflectionLog />
    </div>
  )
}

/* ── Control ────────────────────────────────────────────────────────────── */
function ControlPage() {
  return (
    <div className="h-full p-3 flex gap-3">
      <div className="w-72 shrink-0 flex flex-col gap-3">
        <ControlPanel />
      </div>
      <div className="flex-1 min-w-0">
        <AgentReports />
      </div>
    </div>
  )
}
