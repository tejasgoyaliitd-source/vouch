import React, { useEffect, useState } from 'react'
import { get } from '../api.js'
import { PageHead, Segmented, Pill, InfoTip, inr } from '../ui.jsx'

function Qty({ l }) {
  const max = Math.max(l.qty, l.received, l.billed, 1)
  const rows = [['Ordered', l.qty, '#AAB3C2'], ['Received', l.received, '#5B7BD5'], ['Billed', l.billed, l.billed > l.qty ? '#C2362F' : '#1E7F5C']]
  return (
    <div className="space-y-1">
      {rows.map(([k, v, c]) => (
        <div key={k} className="grid grid-cols-[62px_1fr_40px] items-center gap-2 text-[12px] text-ink-2">
          <span>{k}</span><span className="h-1.5 rounded-full bg-[#F0F0EB]"><span className="block h-1.5 rounded-full" style={{ width: `${(v / max) * 100}%`, background: c }} /></span><span className="text-right text-ink">{v}</span>
        </div>
      ))}
    </div>
  )
}

export default function Vendors() {
  const [r, setR] = useState(null)
  const [tab, setTab] = useState('vendors')
  useEffect(() => { get('/records').then(setR) }, [])
  if (!r) return null
  const s = r.settings
  return (
    <div className="max-w-[1320px]">
      <PageHead title="Vendors and POs">
        <Segmented value={tab} onChange={setTab} options={[['vendors', `Vendors (${r.vendors.length})`], ['pos', `Purchase orders (${r.pos.length})`], ['rules', 'Rules and limits']]} />
      </PageHead>
      {tab === 'vendors' && (
        <div className="panel overflow-hidden">
          <table className="tbl">
            <thead><tr><th>Vendor</th><th>GSTIN</th><th>MSME</th><th>Bank account</th><th>Sends from</th><th>Terms</th></tr></thead>
            <tbody>{r.vendors.map((v) => (
              <tr key={v.vendor_id}>
                <td className="font-medium">{v.name}</td><td className="id">{v.gstin}</td>
                <td>{v.msme ? <Pill tone="blue">{v.msme === 'micro' ? 'Micro' : 'Small'}</Pill> : <span className="text-ink-3">No</span>}</td>
                <td className="id text-ink-2">•••• {v.bank_account.slice(-4)}</td><td className="text-ink-2">{v.email_domains}</td><td className="text-ink-2">{v.payment_terms_days} days</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {tab === 'pos' && (
        <div className="panel overflow-hidden">
          <table className="tbl">
            <thead><tr><th>PO</th><th>Vendor</th><th>Item</th><th className="text-right">Rate</th><th className="w-[34%]">Quantity</th></tr></thead>
            <tbody>{r.pos.flatMap((p) => p.lines.map((l, i) => (
              <tr key={p.po_no + l.line_no}>
                <td className="id">{i === 0 ? p.po_no : ''}</td><td className="text-ink-2">{i === 0 ? p.vendor_name : ''}</td>
                <td>{l.description}</td><td className="text-right">{inr(l.unit_price)}<div className="text-[12px] text-ink-3">GST {l.gst_rate}%</div></td><td><Qty l={l} /></td>
              </tr>
            )))}</tbody>
          </table>
        </div>
      )}
      {tab === 'rules' && (
        <div className="panel divide-y divide-line">
          {[
            ['Unit price tolerance', `±${s.price_tol_pct}% or ${inr(s.price_tol_abs)} per line, whichever is lower`, 'A billed rate inside this band against the PO rate passes without review.'],
            ['Rounding on totals', `±${inr(s.rounding)}`, 'Line items plus tax may differ from the printed total by this much.'],
            ['Automatic approval limit', inr(s.auto_approve_cap), 'Invoices above this need an AP manager to sign off, even when every check passes.'],
            ['Confidence needed on money fields', s.min_conf, 'Totals, tax and GSTINs read below this confidence are confirmed by a person.'],
            ['MSME payment limit', `${s.msme_max_days} days`, 'Micro and small suppliers must be paid within this window (MSMED Act; Section 43B(h)).'],
            ['Oldest invoice accepted', `${s.max_age_days} days`, 'Older invoices are held for review.'],
          ].map(([k, v, tip]) => (
            <div key={k} className="flex items-center justify-between gap-4 px-5 py-3.5 text-[13.5px]">
              <span className="flex items-center gap-1.5">{k}<InfoTip text={tip} /></span><span className="font-medium">{v}</span>
            </div>
          ))}
          <div className="px-5 py-3 text-[12.5px] text-ink-3">Rules version {r.rules_version}. Every decision records the version it used.</div>
        </div>
      )}
    </div>
  )
}
