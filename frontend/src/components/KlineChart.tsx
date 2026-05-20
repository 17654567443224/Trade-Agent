import React, { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
} from 'lightweight-charts'
import { useStore } from '../store/useStore'

export function KlineChart() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  const selectedSymbol = useStore((s) => s.selectedSymbol)
  const symbols = useStore((s) => s.symbols)
  const klines = useStore((s) => s.klines)
  const setSelectedSymbol = useStore((s) => s.setSelectedSymbol)

  // init chart
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1c2128' },
        textColor: '#8b949e',
      },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      crosshair: { mode: 1 },
      timeScale: { borderColor: '#30363d', timeVisible: true },
      rightPriceScale: { borderColor: '#30363d' },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    })
    const series = chart.addCandlestickSeries({
      upColor: '#3fb950',
      downColor: '#f85149',
      borderUpColor: '#3fb950',
      borderDownColor: '#f85149',
      wickUpColor: '#3fb950',
      wickDownColor: '#f85149',
    })
    chartRef.current = chart
    seriesRef.current = series

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, containerRef.current.clientHeight)
      }
    })
    ro.observe(containerRef.current)
    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [])

  // update data when klines or selectedSymbol changes
  useEffect(() => {
    if (!seriesRef.current || !selectedSymbol) return
    // find the best matching key
    const key = Object.keys(klines).find((k) => k.includes(selectedSymbol)) ?? ''
    const candles = klines[key]?.candles ?? []
    if (!candles.length) return

    // 用 Map 按 time 去重（同时间戳保留最新），再升序排列
    const seen = new Map<number, CandlestickData>()
    for (const c of candles) {
      if (!c.open || !c.high || !c.low || !c.close) continue
      const t = typeof c.time === 'number' ? c.time : parseInt(String(c.time))
      seen.set(t, {
        time: t as Time,
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
      })
    }
    const data = Array.from(seen.values()).sort((a, b) => (a.time as number) - (b.time as number))
    if (!data.length) return

    seriesRef.current.setData(data)
    chartRef.current?.timeScale().fitContent()
  }, [klines, selectedSymbol])

  return (
    <div className="flex flex-col h-full bg-[#1c2128] rounded-lg border border-[#30363d] overflow-hidden">
      {/* toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#30363d] min-w-0">
        <span className="text-xs text-[#58a6ff] font-semibold shrink-0">K 线图</span>
        <div className="flex gap-1 ml-2 flex-1 min-w-0 overflow-x-auto">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setSelectedSymbol(sym)}
              className={`px-2 py-0.5 rounded text-xs whitespace-nowrap shrink-0 ${
                selectedSymbol === sym
                  ? 'bg-[#1f6feb] text-white'
                  : 'bg-[#21262d] text-[#8b949e] hover:text-white'
              }`}
            >
              {sym.replace('-SWAP', '').replace('USDT', '/USDT')}
            </button>
          ))}
        </div>
      </div>
      {/* chart */}
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  )
}
