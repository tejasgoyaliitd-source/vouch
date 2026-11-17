import React, { useEffect, useRef, useState } from 'react'

export function useWidth() {
  const ref = useRef(null)
  const [w, setW] = useState(600)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

const nice = (v) => { if (v <= 4) return 4; const p = 10 ** Math.floor(Math.log10(v)); return Math.ceil(v / p * 2) / 2 * p }
const topRound = (x, y, w, h, r) => {
  r = Math.min(r, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}
const rightRound = (x, y, w, h, r) => {
  r = Math.min(r, h / 2, w)
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`
}

export function Legend({ items }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-2">
      {items.map((s) => (
        <span key={s.label} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: s.color }} />{s.label}{s.value !== undefined && <span className="font-medium text-ink">{s.value}</span>}</span>
      ))}
    </div>
  )
}

function Tip({ x, y, children, w }) {
  const left = Math.min(Math.max(x, 70), w - 70)
  return (
    <div className="pointer-events-none absolute z-20 min-w-[170px] -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md bg-ink px-2.5 py-2 text-[12px] text-white shadow-lg" style={{ left, top: y - 8 }}>{children}</div>
  )
}

/* Columns over time, stacked by outcome. */
export function StackedColumns({ data, series, height = 210, label }) {
  const [ref, W] = useWidth()
  const [hi, setHi] = useState(null)
  const pad = { l: 30, r: 4, t: 10, b: 24 }
  const iw = W - pad.l - pad.r, ih = height - pad.t - pad.b
  const totals = data.map((d) => series.reduce((s, k) => s + d[k.key], 0))
  const max = nice(Math.max(...totals, 1))
  const band = iw / data.length, bw = Math.max(3, Math.min(18, band * 0.64))
  const y = (v) => (v / max) * ih
  return (
    <div ref={ref} className="relative" onMouseLeave={() => setHi(null)}>
      <svg width={W} height={height} role="img" aria-label={label}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={pad.l} x2={W - pad.r} y1={pad.t + ih - f * ih} y2={pad.t + ih - f * ih} stroke={f === 0 ? '#D3D3CC' : '#EDEDE8'} />
            <text x={pad.l - 8} y={pad.t + ih - f * ih + 4} textAnchor="end" fontSize="11" fill="#8A8F99">{Math.round(max * f)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = pad.l + i * band + (band - bw) / 2
          let acc = 0
          const segs = series.filter((s) => d[s.key] > 0)
          return (
            <g key={d.date} opacity={hi === null || hi === i ? 1 : 0.45}>
              {segs.map((s, j) => {
                const h = y(d[s.key]), top = pad.t + ih - acc - h
                acc += h
                const gh = Math.max(h - (j < segs.length - 1 ? 0 : 0) - (j > 0 ? 2 : 0), 1)
                return j === segs.length - 1
                  ? <path key={s.key} d={topRound(x, top, bw, gh, 3)} fill={s.color} />
                  : <rect key={s.key} x={x} y={top + (j > 0 ? 0 : 0)} width={bw} height={gh} fill={s.color} />
              })}
            </g>
          )
        })}
        {data.map((d, i) => (i % 7 === (data.length - 1) % 7) && (
          <text key={d.date} x={pad.l + i * band + band / 2} y={height - 6} textAnchor="middle" fontSize="11" fill="#8A8F99">
            {new Date(d.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
          </text>
        ))}
        {data.map((d, i) => <rect key={'h' + d.date} x={pad.l + i * band} y={pad.t} width={band} height={ih} fill="transparent" onMouseEnter={() => setHi(i)} />)}
      </svg>
      {hi !== null && (
        <Tip x={pad.l + hi * band + band / 2} y={pad.t + ih - y(totals[hi])} w={W}>
          <div className="mb-1 font-medium">{new Date(data[hi].date).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</div>
          {series.map((s) => <div key={s.key} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />{s.label}<span className="ml-auto pl-4 font-medium">{data[hi][s.key]}</span></div>)}
          <div className="mt-1 border-t border-white/20 pt-1 text-white/80">Received <span className="float-right pl-4 font-medium text-white">{totals[hi]}</span></div>
        </Tip>
      )}
    </div>
  )
}

/* Horizontal stacked rows (owner by age band). */
export function StackedRows({ rows, colors, bandLabels, label }) {
  const [ref, W] = useWidth()
  const [hi, setHi] = useState(null)
  const lw = 104, rw = 30, rowH = 30, bh = 14
  const max = Math.max(...rows.map((r) => r.total), 1)
  const iw = W - lw - rw
  return (
    <div ref={ref} className="relative" onMouseLeave={() => setHi(null)}>
      <svg width={W} height={rows.length * rowH} role="img" aria-label={label}>
        {rows.map((r, i) => {
          let x = lw
          const segs = r.buckets.map((v, b) => ({ v, b })).filter((s) => s.v > 0)
          return (
            <g key={r.owner} transform={`translate(0 ${i * rowH})`}>
              <text x={0} y={rowH / 2 + 4} fontSize="12.5" fill="#17191E">{r.owner}</text>
              <rect x={lw} y={(rowH - bh) / 2} width={iw} height={bh} rx="3" fill="#F3F3EF" />
              {segs.map((s, j) => {
                const w = (s.v / max) * iw - (j < segs.length - 1 ? 2 : 0)
                const el = j === segs.length - 1
                  ? <path key={s.b} d={rightRound(x, (rowH - bh) / 2, Math.max(w, 2), bh, 3)} fill={colors[s.b]} onMouseEnter={() => setHi({ i, b: s.b, x: x + w / 2 })} />
                  : <rect key={s.b} x={x} y={(rowH - bh) / 2} width={Math.max(w, 1)} height={bh} fill={colors[s.b]} onMouseEnter={() => setHi({ i, b: s.b, x: x + w / 2 })} />
                x += w + 2
                return el
              })}
              <text x={W} y={rowH / 2 + 4} textAnchor="end" fontSize="12.5" fontWeight="500" fill={r.total ? '#17191E' : '#8A8F99'}>{r.total}</text>
            </g>
          )
        })}
      </svg>
      {hi && <Tip x={hi.x} y={hi.i * rowH + 6} w={W}>{rows[hi.i].owner}, {bandLabels[hi.b].toLowerCase()}: <span className="font-medium">{rows[hi.i].buckets[hi.b]}</span></Tip>}
    </div>
  )
}

/* Ranked horizontal bars, one series. */
export function RankedBars({ rows, color = '#3D4250', label }) {
  const max = Math.max(...rows.map((r) => r.n), 1)
  return (
    <ul className="space-y-2.5" aria-label={label}>
      {rows.map((r) => (
        <li key={r.type} className="group grid grid-cols-[minmax(0,170px)_1fr_auto] items-center gap-3 text-[13px]">
          <span className="truncate">{r.type}</span>
          <span className="relative h-2.5 rounded-r-[3px] bg-[#F3F3EF]">
            <span className="absolute inset-y-0 left-0 rounded-r-[3px]" style={{ width: `${(r.n / max) * 100}%`, background: color }} />
          </span>
          <span className="w-28 text-right"><span className="font-medium">{r.n}</span><span className="ml-2 text-ink-3">{r.value ? `₹${(r.value / 1e5).toFixed(1)} L` : ''}</span></span>
        </li>
      ))}
    </ul>
  )
}

/* Weekly payables, stacked by supplier type, values labelled. */
export function WeekColumns({ weeks, series, height = 190, label, fmt }) {
  const [ref, W] = useWidth()
  const [hi, setHi] = useState(null)
  const pad = { t: 22, b: 24 }
  const ih = height - pad.t - pad.b
  const totals = weeks.map((w) => series.reduce((s, k) => s + w[k.key], 0))
  const max = Math.max(...totals, 1)
  const band = W / weeks.length, bw = Math.min(56, band * 0.5)
  return (
    <div ref={ref} className="relative" onMouseLeave={() => setHi(null)}>
      <svg width={W} height={height} role="img" aria-label={label}>
        <line x1={0} x2={W} y1={pad.t + ih} y2={pad.t + ih} stroke="#D3D3CC" />
        {weeks.map((w, i) => {
          const x = i * band + (band - bw) / 2
          let acc = 0
          const segs = series.filter((s) => w[s.key] > 0)
          return (
            <g key={w.label} onMouseEnter={() => setHi(i)}>
              <rect x={i * band} y={0} width={band} height={height} fill="transparent" />
              {segs.map((s, j) => {
                const h = (w[s.key] / max) * ih, top = pad.t + ih - acc - h
                acc += h
                const gh = Math.max(h - (j > 0 ? 2 : 0), 1)
                return j === segs.length - 1 ? <path key={s.key} d={topRound(x, top, bw, gh, 4)} fill={s.color} /> : <rect key={s.key} x={x} y={top} width={bw} height={gh} fill={s.color} />
              })}
              <text x={x + bw / 2} y={pad.t + ih - acc - 7} textAnchor="middle" fontSize="12" fontWeight="500" fill="#17191E">{fmt(totals[i])}</text>
              <text x={x + bw / 2} y={height - 6} textAnchor="middle" fontSize="11" fill="#8A8F99">{i === 0 ? 'This week' : `Wk of ${w.label}`}</text>
            </g>
          )
        })}
      </svg>
      {hi !== null && (
        <Tip x={hi * band + band / 2} y={pad.t + 10} w={W}>
          <div className="mb-1 font-medium">{weeks[hi].count} invoices due</div>
          {series.map((s) => <div key={s.key} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />{s.label}<span className="ml-auto pl-4 font-medium">{fmt(weeks[hi][s.key])}</span></div>)}
        </Tip>
      )}
    </div>
  )
}
