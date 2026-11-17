import React, { useEffect, useState } from 'react'
import { ShieldCheck, ShieldAlert, Download } from 'lucide-react'
import { get } from '../api.js'
import { PageHead, InfoTip, fmtDay, fmtTime } from '../ui.jsx'
import { go } from '../App.jsx'

const DOT = { ok: 'bg-vouch', warn: 'bg-hold', fail: 'bg-alert' }

export default function Audit() {
  const [a, setA] = useState(null)
  useEffect(() => { get('/audit').then(setA) }, [])
  if (!a) return null
  return (
    <div className="max-w-[1320px]">
      <PageHead title="Audit trail">
        <span className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium ${a.chain_ok ? 'bg-vouch-50 text-vouch' : 'bg-alert-50 text-alert'}`}>
          {a.chain_ok ? <ShieldCheck size={15} /> : <ShieldAlert size={15} />}{a.chain_ok ? 'Log intact' : 'Log altered'}
          <InfoTip text="Each entry stores a hash of the entry before it. Changing any past entry breaks the chain, and this check fails." />
        </span>
        <a className="btn" href="/api/export/erp.csv"><Download size={15} />Approved bills for the ERP</a>
      </PageHead>
      <div className="panel overflow-hidden">
        <table className="tbl">
          <thead><tr><th>When</th><th>Invoice</th><th>Step</th><th>What happened</th><th>Entry hash</th></tr></thead>
          <tbody>
            {a.events.map((e) => (
              <tr key={e.event_id} className={e.run_id ? 'clickable' : ''} onClick={() => e.run_id && go(`processing/${e.run_id}`)}>
                <td className="whitespace-nowrap text-ink-2">{fmtDay(e.ts)}, {fmtTime(e.ts)}</td>
                <td className="id whitespace-nowrap">{e.invoice_no || '—'}</td>
                <td className="whitespace-nowrap"><span className="inline-flex items-center gap-1.5"><span className={`h-1.5 w-1.5 rounded-full ${DOT[e.status] || 'bg-ink-3'}`} />{e.stage}</span></td>
                <td className="max-w-[560px] text-ink-2">{e.summary}</td>
                <td className="id text-ink-3">{e.hash.slice(0, 12)}</td>
              </tr>
            ))}
            {a.events.length === 0 && <tr><td colSpan={5} className="py-10 text-center text-ink-3">Entries appear as invoices are processed.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
