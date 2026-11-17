import React, { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'
import { get } from '../api.js'
import { InfoTip, Panel, PageHead, Segmented, inrShort } from '../ui.jsx'
import { StackedColumns, StackedRows, RankedBars, WeekColumns, Legend } from '../charts.jsx'
import { useAuth } from '../auth.jsx'

const OUTCOMES = [
  { key: 'straight', label: 'Straight-through', color: '#1E7F5C' },
  { key: 'reviewed', label: 'Approved after review', color: '#5B7BD5' },
  { key: 'open', label: 'Waiting on a person', color: '#B26A0A' },
  { key: 'rejected', label: 'Rejected', color: '#8E6BB0' },
]
const AGE = ['#DDA65A', '#C47F22', '#9E5B08', '#653704']
const PAY = [{ key: 'msme', label: 'MSME suppliers', color: '#5B7BD5' }, { key: 'other', label: 'Other suppliers', color: '#B9BEC6' }]
const hours = (h) => (h == null ? '—' : h < 24 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`)

function Delta({ value, unit, goodWhen, days }) {
  if (value === null || value === undefined || isNaN(value) || Math.abs(value) < 0.05) return <span className="text-ink-3">No change on the previous {days} days</span>
  const up = value > 0
  const good = goodWhen === 'up' ? up : !up
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className="inline-flex items-center gap-1 text-ink-2">
      <Icon size={14} className={goodWhen === 'neutral' ? 'text-ink-3' : good ? 'text-vouch' : 'text-alert'} aria-hidden="true" />
      {up ? '+' : '−'}{Math.abs(value).toFixed(1)}{unit} on the previous {days} days
    </span>
  )
}

function Kpi({ label, tip, value, foot }) {
  return (
    <div className="min-w-0 px-5 py-4">
      <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-ink-2">{label}<InfoTip text={tip} /></div>
      <div className="mt-1.5 text-[26px] font-semibold leading-none tracking-tight">{value}</div>
      <div className="mt-2 text-[12px]">{foot}</div>
    </div>
  )
}

export default function Overview() {
  const { user } = useAuth()
  const [days, setDays] = useState(30)
  const [d, setD] = useState(null)
  useEffect(() => { get(`/dashboard?days=${days}`).then(setD) }, [days])
  const first = user.name.split(' ')[0]

  return (
    <div className="max-w-[1320px]">
      <PageHead title={`Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, ${first}`}>
        <Segmented value={days} onChange={setDays} options={[[7, '7 days'], [30, '30 days'], [60, '60 days']]} />
      </PageHead>
      {!d ? <div className="h-96 animate-pulse rounded-xl bg-white" /> : (
        <>
          <section className="panel grid grid-cols-2 divide-line lg:grid-cols-5 lg:divide-x" aria-label="Key figures">
            <Kpi label="Invoices processed" tip="Invoices received in the period, whatever the outcome." value={d.kpi.processed}
              foot={<span className="text-ink-2">{inrShort(d.kpi.value)} in value</span>} />
            <Kpi label="Straight-through rate" tip="Share of invoices approved without anyone touching them."
              value={`${d.kpi.stp}%`} foot={<Delta value={d.kpi.stp - d.prev.stp} unit=" pts" goodWhen="up" days={days} />} />
            <Kpi label="Time to decision" tip="Median time from receipt to final decision, for invoices a person had to review. Automatic decisions take seconds."
              value={hours(d.kpi.human_hours)} foot={d.prev.human_hours ? <Delta value={(d.kpi.human_hours || 0) - d.prev.human_hours} unit=" h" goodWhen="down" days={days} /> : null} />
            <Kpi label="Open exceptions" tip="Invoices waiting on a person right now: holds, security holds and sign-offs. Value at risk is what cannot be paid until they clear."
              value={d.kpi.open_exceptions} foot={<span className="text-ink-2">{inrShort(d.kpi.at_risk)} at risk{d.kpi.stale ? `, ${d.kpi.stale} older than 3 days` : ''}</span>} />
            <Kpi label="Payments protected" tip="Value of duplicate invoices rejected and payments blocked because bank details changed."
              value={inrShort(d.kpi.protected)} foot={<Delta value={(d.kpi.protected - d.prev.protected) / 1e5} unit=" L" goodWhen="neutral" days={days} />} />
          </section>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
            <Panel title="Invoices received" tip="Each day's invoices, coloured by where they ended up.">
              <div className="mb-3"><Legend items={OUTCOMES.map((s) => ({ ...s, value: d.daily.reduce((a, x) => a + x[s.key], 0) }))} /></div>
              <StackedColumns data={d.daily} series={OUTCOMES} label="Invoices received per day by outcome" />
            </Panel>
            <Panel title="Waiting on people" tip="Open exceptions by who must act and how long they have waited.">
              <div className="mb-4"><Legend items={d.age_labels.map((l, i) => ({ label: l, color: AGE[i] }))} /></div>
              <StackedRows rows={d.ageing} colors={AGE} bandLabels={d.age_labels} label="Open exceptions by owner and age" />
            </Panel>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Panel title="Why invoices stopped" tip="Checks that sent an invoice to a person in the period, with the value involved.">
              <RankedBars rows={d.by_type.slice(0, 7)} label="Exceptions by type" />
            </Panel>
            <Panel title="Payables due" tip="Approved, unpaid invoices by week due. MSME suppliers must be paid within 45 days by law.">
              <div className="mb-2"><Legend items={PAY} /></div>
              <WeekColumns weeks={d.payables} series={PAY} fmt={inrShort} label="Payables due by week" />
            </Panel>
            <Panel title="Vendors to watch" tip="Vendors whose invoices most often needed a person in the period." pad={false}>
              <table className="tbl">
                <thead><tr><th>Vendor</th><th className="text-right">Invoices</th><th>Needed a person</th></tr></thead>
                <tbody>
                  {d.vendors.map((v) => (
                    <tr key={v.vendor}>
                      <td className="max-w-[160px] truncate">{v.vendor}</td>
                      <td className="text-right text-ink-2">{v.n}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          <span className="relative h-1.5 w-16 rounded-full bg-[#F0F0EB]"><span className="absolute inset-y-0 left-0 rounded-full bg-hold" style={{ width: `${v.rate}%` }} /></span>
                          <span className="text-[12.5px]">{v.rate}%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </div>
        </>
      )}
    </div>
  )
}
