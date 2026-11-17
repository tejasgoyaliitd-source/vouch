import React, { useEffect, useMemo, useState } from 'react'
import { Search, Download } from 'lucide-react'
import { get } from '../api.js'
import { PageHead, Segmented, StatusChip, inr, fmtDate, fmtDay } from '../ui.jsx'
import { go } from '../App.jsx'

const TABS = [['all', 'All'], ['approved', 'Approved'], ['open', 'Waiting'], ['rejected', 'Rejected']]

export default function Invoices() {
  const [rows, setRows] = useState([])
  const [tab, setTab] = useState('all')
  const [qy, setQy] = useState('')
  const [limit, setLimit] = useState(60)
  useEffect(() => { get('/invoices').then(setRows) }, [])
  const shown = useMemo(() => rows.filter((r) =>
    (tab === 'all' || (tab === 'open' ? ['hold', 'security', 'signoff'].includes(r.outcome) : r.outcome === tab)) &&
    (!qy || `${r.invoice_no} ${r.vendor_name} ${r.total}`.toLowerCase().includes(qy.toLowerCase()))), [rows, tab, qy])

  return (
    <div className="max-w-[1320px]">
      <PageHead title="Invoices">
        <label className="flex h-8 w-64 items-center gap-2 rounded-lg border border-line-2 bg-white px-2.5 text-[13px] focus-within:border-ink-3">
          <Search size={15} className="text-ink-3" aria-hidden="true" />
          <input value={qy} onChange={(e) => setQy(e.target.value)} placeholder="Invoice number, vendor or amount" className="w-full bg-transparent outline-none placeholder:text-ink-3" />
        </label>
        <a className="btn" href="/api/export/erp.csv"><Download size={15} />Export approved for ERP</a>
      </PageHead>
      <div className="mb-3"><Segmented value={tab} onChange={setTab} options={TABS} /></div>
      <div className="panel overflow-hidden">
        <table className="tbl">
          <thead><tr><th>Received</th><th>Invoice</th><th>Vendor</th><th className="text-right">Amount</th><th>Status</th><th>Handled</th><th>Due</th></tr></thead>
          <tbody>
            {shown.slice(0, limit).map((r) => (
              <tr key={r.invoice_id} className="clickable" onClick={() => go(`invoice/${r.invoice_id}`)}>
                <td className="whitespace-nowrap text-ink-2">{fmtDay(r.received_at || r.decided_at)}</td>
                <td className="id">{r.invoice_no || '—'}</td>
                <td className="max-w-[240px] truncate">{r.vendor_name || 'Unknown vendor'}</td>
                <td className="text-right font-medium">{inr(r.total)}</td>
                <td><StatusChip outcome={r.outcome} /></td>
                <td className="text-ink-2">{r.outcome === 'approved' ? (r.touched ? 'After review' : 'Straight-through') : r.outcome === 'rejected' ? (r.touched ? 'After review' : 'Automatically') : 'Waiting'}</td>
                <td className="whitespace-nowrap text-ink-2">{r.outcome === 'approved' ? (r.paid ? 'Paid' : fmtDate(r.due_date)) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length > limit && <div className="border-t border-line p-3 text-center"><button className="btn btn-sm" onClick={() => setLimit((l) => l + 100)}>Show more ({shown.length - limit})</button></div>}
        {shown.length === 0 && <div className="py-10 text-center text-[13px] text-ink-3">No invoices match</div>}
      </div>
    </div>
  )
}
