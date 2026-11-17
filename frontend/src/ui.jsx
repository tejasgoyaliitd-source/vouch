import React, { useState } from 'react'
import { CheckCircle2, Clock, PenLine, ShieldAlert, XCircle, Loader2, Info } from 'lucide-react'

/* ---------- formatting ---------- */
export function inr(n) {
  if (n === null || n === undefined || n === '') return '—'
  const v = Number(n)
  return '₹' + v.toLocaleString('en-IN', { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 })
}
export function inrShort(n) {
  const v = Number(n || 0)
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)} K`
  return `₹${Math.round(v)}`
}
export const fmtDate = (s) => (s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
export const fmtDay = (s) => (s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '—')
export const fmtTime = (s) => (s ? new Date(s).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '')
export function ago(s) {
  if (!s) return ''
  const h = (Date.now() - new Date(s).getTime()) / 3.6e6
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`
  if (h < 24) return `${Math.round(h)} h`
  return `${Math.round(h / 24)} d`
}

/* ---------- brand ---------- */
export function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <mask id="voucher-notch">
          <rect width="32" height="32" fill="white" />
          <circle cx="3" cy="16" r="3.6" fill="black" />
          <circle cx="29" cy="16" r="3.6" fill="black" />
        </mask>
      </defs>
      <rect x="3" y="5" width="26" height="22" rx="6" fill="#17191E" mask="url(#voucher-notch)" />
      <path d="M10.5 16.2l3.6 3.6 7.6-8" fill="none" stroke="#4CC38A" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/* ---------- status ---------- */
export const STATUS = {
  approved: { label: 'Approved', icon: CheckCircle2, cls: 'bg-vouch-50 text-vouch', dot: 'bg-vouch' },
  signoff: { label: 'Needs sign-off', icon: PenLine, cls: 'bg-review-50 text-review', dot: 'bg-review' },
  hold: { label: 'On hold', icon: Clock, cls: 'bg-hold-50 text-hold', dot: 'bg-hold' },
  security: { label: 'Security hold', icon: ShieldAlert, cls: 'bg-alert-50 text-alert', dot: 'bg-alert' },
  rejected: { label: 'Rejected', icon: XCircle, cls: 'bg-reject-50 text-reject', dot: 'bg-reject' },
  running: { label: 'Processing', icon: Loader2, cls: 'bg-paper text-ink-2', dot: 'bg-ink-3' },
}

export function StatusChip({ outcome, label }) {
  const s = STATUS[outcome] || STATUS.running
  const Icon = s.icon
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium whitespace-nowrap ${s.cls}`}>
      <Icon size={13} strokeWidth={2.2} className={outcome === 'running' ? 'animate-spin' : ''} aria-hidden="true" />{label || s.label}
    </span>
  )
}

export function Pill({ children, tone = 'plain' }) {
  const t = { plain: 'bg-paper text-ink-2 border border-line', blue: 'bg-review-50 text-review', green: 'bg-vouch-50 text-vouch', amber: 'bg-hold-50 text-hold', red: 'bg-alert-50 text-alert' }[tone]
  return <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] font-medium whitespace-nowrap ${t}`}>{children}</span>
}

/* Definitions live behind a hover, not under every heading. */
export function InfoTip({ text, side = 'bottom' }) {
  return (
    <span className="group relative inline-flex" tabIndex={0} aria-label={text}>
      <Info size={13} className="text-ink-3 group-hover:text-ink-2" aria-hidden="true" />
      <span role="tooltip" className={`pointer-events-none absolute left-1/2 z-30 w-60 -translate-x-1/2 rounded-md bg-ink px-2.5 py-2 text-[12px] font-normal leading-snug text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus:opacity-100 ${side === 'top' ? 'bottom-6' : 'top-6'}`}>{text}</span>
    </span>
  )
}

export function Panel({ title, tip, right, children, className = '', pad = true }) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <div className="panel-head">
          <h2 className="panel-title">{title}{tip && <InfoTip text={tip} />}</h2>
          {right}
        </div>
      )}
      <div className={pad ? 'p-4' : 'pt-2'}>{children}</div>
    </section>
  )
}

export function PageHead({ title, children, meta }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">{title}</h1>
        {meta && <div className="mt-1 text-[13px] text-ink-2">{meta}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </header>
  )
}

export function Segmented({ value, options, onChange }) {
  return (
    <div className="inline-flex rounded-lg border border-line-2 bg-white p-0.5">
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`h-7 rounded-md px-3 text-[12.5px] font-medium transition ${value === v ? 'bg-ink text-white' : 'text-ink-2 hover:text-ink'}`}>{label}</button>
      ))}
    </div>
  )
}

/* ---------- decision ---------- */
export function DecisionCard({ inv, actions }) {
  if (!inv || inv.outcome === 'running') return null
  const s = STATUS[inv.outcome] || STATUS.running
  const Icon = s.icon
  return (
    <div className="panel relative overflow-hidden p-5">
      {inv.outcome === 'approved' && (
        <div className="stamp pointer-events-none absolute right-5 top-4 select-none rounded-md border-[2.5px] border-vouch px-2.5 py-0.5 text-[15px] font-semibold uppercase tracking-[0.18em] text-vouch/90" aria-hidden="true">Vouched</div>
      )}
      <div className={`inline-flex items-center gap-1.5 text-[17px] font-semibold ${s.cls.split(' ').find((c) => c.startsWith('text-'))}`}>
        <Icon size={18} strokeWidth={2.2} aria-hidden="true" />{inv.outcome_title}
      </div>
      <p className="mt-2 max-w-[62ch] text-[13.5px] leading-relaxed text-ink-2">{inv.outcome_reason}</p>
      {inv.next_step && <p className="mt-3 max-w-[62ch] border-l-2 border-line-2 pl-3 text-[13.5px] text-ink"><span className="font-medium">Next.</span> {inv.next_step}</p>}
      {actions && <div className="mt-4 flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

/* ---------- document viewer ---------- */
export const FIELD_LABEL = {
  invoice_no: 'Invoice number', invoice_date: 'Invoice date', supplier_gstin: 'Supplier GSTIN', buyer_gstin: 'Buyer GSTIN', po_no: 'PO on invoice',
  subtotal: 'Subtotal', tax_igst: 'IGST', tax_cgst: 'CGST', tax_sgst: 'SGST', total: 'Total', bank_account: 'Bank account', ifsc: 'IFSC', irn: 'IRN',
}
const MONEY = new Set(['subtotal', 'tax_igst', 'tax_cgst', 'tax_sgst', 'total'])
const MONO = new Set(['invoice_no', 'supplier_gstin', 'buyer_gstin', 'po_no', 'ifsc', 'irn', 'bank_account'])
export function fieldValue(f) {
  if (MONEY.has(f.name)) return inr(f.value)
  if (f.name === 'bank_account') return '•••• ' + String(f.value).slice(-4)
  if (f.name === 'irn') return String(f.value).slice(0, 14) + '…'
  return f.value
}

export function DocViewer({ docId, fields = [] }) {
  const [hover, setHover] = useState(null)
  if (!docId) return <div className="flex h-72 items-center justify-center rounded-lg border border-dashed border-line-2 text-[13px] text-ink-3">The page appears here once it has been read</div>
  return (
    <div>
      <div className="relative overflow-hidden rounded-md border border-line bg-paper">
        <img src={`/api/documents/${docId}/preview`} alt="First page of the invoice" className="block w-full" />
        {fields.filter((f) => f.bbox).map((f) => {
          const [x0, y0, x1, y1] = f.bbox
          const low = f.confidence < 0.85
          return (
            <div key={f.name} onMouseEnter={() => setHover(f.name)} onMouseLeave={() => setHover(null)}
              className={`absolute rounded-[3px] border-[1.5px] transition ${low ? 'border-hold bg-hold/15' : 'border-review/80 bg-review/10'} ${hover === f.name ? 'ring-4 ring-review/25' : ''}`}
              style={{ left: `${x0 * 100 - 0.4}%`, top: `${y0 * 100 - 0.3}%`, width: `${(x1 - x0) * 100 + 0.8}%`, height: `${(y1 - y0) * 100 + 0.6}%` }}
              title={`${FIELD_LABEL[f.name] || f.name}: ${f.value}`} />
          )
        })}
      </div>
      {fields.length > 0 && (
        <table className="tbl mt-3">
          <thead><tr><th>Field</th><th>Value</th><th>Read from</th><th className="text-right">Confidence</th></tr></thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.name} onMouseEnter={() => setHover(f.name)} onMouseLeave={() => setHover(null)} className={hover === f.name ? 'bg-review-50/60' : ''}>
                <td className="text-ink-2">{FIELD_LABEL[f.name] || f.name}</td>
                <td className={`font-medium ${MONO.has(f.name) ? 'id' : ''}`}>{fieldValue(f)}</td>
                <td className={f.source.includes('differs') ? 'text-hold' : 'text-ink-2'}>{{ 'e-invoice QR': 'Signed QR', OCR: 'OCR', 'text layer': 'Text layer', Word: 'Word file' }[f.source] || f.source}</td>
                <td className={`text-right ${f.confidence < 0.85 ? 'font-semibold text-hold' : 'text-ink-2'}`}>{Number(f.confidence).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
