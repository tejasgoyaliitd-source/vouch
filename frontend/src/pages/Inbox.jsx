import React, { useEffect, useRef, useState } from 'react'
import { Paperclip, Upload, Mail, Smartphone } from 'lucide-react'
import { get, post, tooBig } from '../api.js'
import { PageHead, Segmented, StatusChip, fmtDay, fmtTime } from '../ui.jsx'
import { go } from '../App.jsx'

export default function Inbox() {
  const [tab, setTab] = useState('new')
  const [samples, setSamples] = useState([])
  const [docs, setDocs] = useState([])
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState('')
  const fileRef = useRef(null)
  useEffect(() => { get('/samples').then(setSamples); get('/documents').then(setDocs) }, [])

  // An email leaves "To process" once it has been processed, as it would in a real inbox. Restore starting data brings it back.
  const waiting = samples.filter((s) => !docs.some((d) => d.filename === s.attachment))
  const process = async (file) => { setBusy(file); const r = await post(`/runs/sample/${encodeURIComponent(file)}`); go(`processing/${r.run_id}`) }
  const upload = async (f) => {
    if (!f) return
    const big = await tooBig(f)
    setErr(big)
    if (big) return
    const fd = new FormData(); fd.append('file', f)
    try { const r = await post('/runs/upload', fd); go(`processing/${r.run_id}`) } catch (e) { setErr('Upload failed: ' + e.message) }
  }

  return (
    <div className="max-w-[1100px]">
      <PageHead title="Inbox" meta={<span className="inline-flex items-center gap-1.5"><Mail size={14} aria-hidden="true" />ap@sharmacomponents.in</span>}>
        <input ref={fileRef} type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.docx,.eml" onChange={(e) => upload(e.target.files[0])} />
        <button className="btn" onClick={() => fileRef.current.click()}><Upload size={15} aria-hidden="true" />Upload a file</button>
      </PageHead>
      {err && <p className="mb-4 rounded-lg border border-alert/30 bg-alert-50 px-3 py-2 text-[13px] text-alert">{err}</p>}
      <div className="mb-3"><Segmented value={tab} onChange={setTab} options={[['new', `To process (${waiting.length})`], ['done', `Processed (${docs.length})`]]} /></div>

      {tab === 'new' && (
        <ul className="panel divide-y divide-line">
          {waiting.length === 0 && <li className="py-8 text-center text-[13px] text-ink-3">Inbox clear. Everything has been processed.</li>}
          {waiting.map((s) => (
            <li key={s.file} className="grid grid-cols-[36px_minmax(0,220px)_minmax(0,1fr)_auto_auto] items-center gap-4 px-4 py-3.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-paper text-ink-2">{s.channel === 'email' ? <Mail size={16} /> : <Smartphone size={16} />}</span>
              <div className="min-w-0">
                <div className="truncate text-[13.5px] font-medium">{s.vendor}</div>
                <div className="truncate text-[12.5px] text-ink-2">{s.source}</div>
              </div>
              <div className="min-w-0">
                <div className="truncate text-[13.5px]">{s.subject}</div>
                <div className="flex items-center gap-1.5 truncate text-[12.5px] text-ink-3"><Paperclip size={12} aria-hidden="true" /><span className="truncate">{s.attachment}</span></div>
              </div>
              <span className="text-[12.5px] text-ink-3">{fmtDay(s.received_at)}, {fmtTime(s.received_at)}</span>
              <button className="btn-ink btn-sm" onClick={() => process(s.file)} disabled={!!busy}>{busy === s.file ? 'Starting' : 'Process'}</button>
            </li>
          ))}
        </ul>
      )}

      {tab === 'done' && (
        <div className="panel overflow-hidden">
          <table className="tbl">
            <thead><tr><th>Received</th><th>From</th><th>Subject or file</th><th>Read as</th><th>Outcome</th></tr></thead>
            <tbody>
              {docs.length === 0 && <tr><td colSpan={5} className="py-8 text-center text-ink-3">Nothing processed yet. Pick something from To process.</td></tr>}
              {docs.map((d) => (
                <tr key={d.doc_id} className="clickable" onClick={() => d.run_id && go(`processing/${d.run_id}`)}>
                  <td className="whitespace-nowrap text-ink-2">{fmtDay(d.received_at)}, {fmtTime(d.received_at)}</td>
                  <td>{d.sender || 'Uploaded'}</td>
                  <td className="max-w-[320px] truncate">{d.subject || d.filename}</td>
                  <td className="text-ink-2">{d.classified_as || 'Reading'}</td>
                  <td>{d.outcome ? <StatusChip outcome={d.outcome} /> : <span className="text-ink-3">Not processed</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
