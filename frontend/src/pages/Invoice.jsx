import React, { useEffect, useState } from 'react'
import { ArrowLeft, Check, X, AlertTriangle, Activity } from 'lucide-react'
import { get } from '../api.js'
import { DecisionCard, DocViewer, Panel, StatusChip, inr, fmtDate, fmtTime, fmtDay } from '../ui.jsx'
import { Draft } from './Exceptions.jsx'
import { go } from '../App.jsx'

const QUESTIONS = [
  [1, 'Is it a genuine invoice from a vendor we deal with?'], [2, 'Did we order it?'], [3, 'Did we receive it?'], [4, 'Is the amount right?'],
  [5, 'Have we already paid it?'], [6, 'Are we paying the right account?'], [7, 'Is the tax right?'], [8, 'When must it be paid?'], [0, 'Can it be approved without sign-off?'],
]
const OWNER = { ap: 'AP desk', procurement: 'Procurement', stores: 'Stores', vendor: 'Vendor', ap_manager: 'AP manager' }

function Icon({ o }) {
  if (o === 'pass') return <Check size={15} className="mt-0.5 text-vouch" />
  if (o === 'fail') return <X size={15} className="mt-0.5 text-alert" />
  if (o === 'warn') return <AlertTriangle size={14} className="mt-0.5 text-hold" />
  return <span className="ml-1 mt-2 h-1.5 w-1.5 rounded-full bg-ink-3" />
}

function Balance({ l }) {
  const max = Math.max(l.po_qty, l.received, l.billed_before + l.qty)
  const pct = (v) => `${(v / max) * 100}%`
  const fit = Math.max(0, Math.min(l.qty, l.po_qty - l.billed_before)), over = l.qty - fit
  return (
    <div>
      <div className="relative h-2.5 rounded-full bg-[#F0F0EB]">
        <div className="absolute inset-y-0 left-0 rounded-l-full bg-[#AAB3C2]" style={{ width: pct(l.billed_before) }} />
        <div className="absolute inset-y-0 bg-vouch" style={{ left: pct(l.billed_before), width: pct(fit) }} />
        <div className="absolute inset-y-0 rounded-r-full bg-alert" style={{ left: pct(l.billed_before + fit), width: pct(over) }} />
        <div className="absolute -inset-y-1 w-0.5 bg-ink" style={{ left: pct(l.po_qty) }} title="Ordered quantity" />
      </div>
      <div className="mt-1.5 text-[12px] text-ink-2">Billed before {l.billed_before}, this invoice {l.qty}{over > 0 ? `, ${over} beyond the PO` : ''}. Ordered {l.po_qty}, received {l.received}.</div>
    </div>
  )
}

export default function Invoice({ id }) {
  const [inv, setInv] = useState(null)
  const load = () => get(`/invoices/${id}`).then(setInv)
  useEffect(() => { load() }, [id])
  if (!inv) return null
  const openTask = inv.tasks.find((t) => t.status !== 'done' && t.draft_body)

  return (
    <div className="max-w-[1320px]">
      <button className="mb-3 inline-flex items-center gap-1 text-[13px] text-ink-2 hover:text-ink" onClick={() => history.back()}><ArrowLeft size={14} />Back</button>
      <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2"><span className="id text-[14px]">{inv.invoice_no || 'No number'}</span><StatusChip outcome={inv.outcome} /></div>
          <h1 className="mt-1 text-[22px] font-semibold tracking-tight">{inv.vendor_name || 'Unknown vendor'} <span className="font-normal text-ink-2">{inr(inv.total)}</span></h1>
          <p className="mt-1 text-[13px] text-ink-2">
            {inv.document?.channel === 'email' ? `Email from ${inv.document.sender}` : inv.document ? 'Uploaded' : 'Imported from history'}, invoice dated {fmtDate(inv.invoice_date)}
            {inv.po_no ? `, ${inv.po_no}${inv.po_suggested ? ' (suggested)' : ''}` : ''}{inv.due_date ? `, due ${fmtDate(inv.due_date)}` : ''}
          </p>
        </div>
        {inv.run_id && <button className="btn" onClick={() => go(`processing/${inv.run_id}`)}><Activity size={15} />Replay processing</button>}
      </header>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <DecisionCard inv={{ ...inv, outcome_reason: inv.outcome_reason || (inv.source === 'history' ? 'Decided before this view was opened; see the timeline.' : ''), }} />
          {inv.lines.some((l) => l.po_qty != null) && (
            <Panel title="Against the PO and receipts" pad={false}>
              <table className="tbl">
                <thead><tr><th>Item</th><th className="text-right">Rate</th><th className="w-[48%]">Quantity</th></tr></thead>
                <tbody>
                  {inv.lines.map((l) => (
                    <tr key={l.line_no}>
                      <td><div className="font-medium">{l.description}</div><div className="text-[12px] text-ink-3">{l.po_description ? `Matched to ${l.po_no} line ${l.po_line}` : 'Not on the PO'}</div></td>
                      <td className="text-right">{inr(l.unit_price)}{l.po_price != null && Math.abs(l.unit_price - l.po_price) > 0.01 && <div className="text-[12px] text-alert">PO {inr(l.po_price)}</div>}</td>
                      <td>{l.po_qty != null ? <Balance l={l} /> : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
          {inv.rules.length > 0 && (
            <Panel title="Checks" pad={false}>
              <div className="divide-y divide-line">
                {QUESTIONS.map(([q, text]) => {
                  const rs = inv.rules.filter((r) => r.question === q)
                  if (!rs.length) return null
                  return (
                    <div key={q} className="px-4 py-3">
                      <div className="mb-1.5 text-[13px] font-semibold">{text}</div>
                      {rs.map((r) => <div key={r.rule_id} className="grid grid-cols-[20px_1fr] gap-1.5 text-[13px] leading-relaxed"><Icon o={r.outcome} /><span className="text-ink-2">{r.detail}</span></div>)}
                    </div>
                  )
                })}
              </div>
            </Panel>
          )}
          {inv.document && <Panel title="Document"><DocViewer docId={inv.doc_id} fields={inv.fields} /></Panel>}
        </div>

        <div className="space-y-4">
          {inv.tasks.length > 0 && (
            <Panel title="Follow-up" pad={false}>
              <ul className="divide-y divide-line">
                {inv.tasks.map((t) => (
                  <li key={t.task_id} className="px-4 py-3">
                    <div className="flex items-center justify-between text-[13px]"><span className="font-medium">{OWNER[t.owner_role]}</span><span className="text-ink-3">{t.status === 'done' ? 'Resolved' : t.status === 'sent' ? 'Message sent' : 'Open'}</span></div>
                    <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{t.ask}</p>
                  </li>
                ))}
              </ul>
              {openTask && <div className="border-t border-line p-4"><div className="mb-2 text-[13px] font-semibold">Drafted message</div><Draft task={openTask} onSent={load} /></div>}
            </Panel>
          )}
          <Panel title="Timeline" pad={false}>
            <ol className="px-4 py-2">
              {inv.events.length === 0 && <li className="py-2 text-[13px] text-ink-3">Received {fmtDay(inv.received_at)}, decided {fmtDay(inv.decided_at)}{inv.resolved_at ? `, resolved ${fmtDay(inv.resolved_at)}` : ''}</li>}
              {inv.events.map((e, i) => (
                <li key={i} className="grid grid-cols-[56px_1fr] gap-2 py-1.5 text-[12.5px]">
                  <span className="text-ink-3">{fmtTime(e.ts)}</span>
                  <span><span className="font-medium text-ink">{e.stage}.</span> <span className="text-ink-2">{e.summary}</span></span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  )
}
