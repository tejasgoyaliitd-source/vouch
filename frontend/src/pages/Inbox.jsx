import React, { useEffect, useRef, useState } from 'react'
import { Paperclip, Upload, Mail, Smartphone, Play, FlaskConical, Download, Check, Minus } from 'lucide-react'
import { get, post, tooBig } from '../api.js'
import { InfoTip, PageHead, Segmented, StatusChip, STATUS, fmtDay, fmtTime, inr } from '../ui.jsx'
import { go } from '../App.jsx'
import { StageTrack, StepLegend, StepMap, byArrival, whyLine, useRunner } from '../runner.jsx'

const ACTIVE = ['queued', 'starting', 'running']
const readShowTests = () => { try { return localStorage.getItem('vouch.showTests') !== '0' } catch { return true } }

function Switch({ on, onChange }) {
  return (
    <button role="switch" aria-checked={on} onClick={() => onChange(!on)}
      className="inline-flex h-8 items-center gap-2 rounded-[7px] border border-line-2 bg-white px-3 text-[13px] font-medium text-ink hover:bg-paper">
      <span className={`relative h-[18px] w-8 shrink-0 rounded-full transition-colors ${on ? 'bg-vouch' : 'bg-line-2'}`} aria-hidden="true">
        <span className={`absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow transition-all ${on ? 'left-[16px]' : 'left-[2px]'}`} />
      </span>
      Process on arrival
    </button>
  )
}

// What the row says under its step map: where the run is now, or how it ended and why.
function StatusLine({ run, expect }) {
  const events = run.events || []
  const steps = events.filter((e) => e.stage_no >= 1 && e.stage_no <= 12)
  if (run.state === 'queued') {
    return (
      <p className="flex items-center gap-1.5 text-[12.5px] text-ink-3">
        Queued. Invoices run one at a time, oldest first.
        <InfoTip text="So two bills against the same PO are always checked in the order they arrived, and the second one sees what the first one billed." />
      </p>
    )
  }
  if (run.state === 'starting' || (run.state === 'running' && !steps.length)) return <p className="text-[12.5px] text-ink-3">Starting</p>
  if (run.state === 'running') {
    const last = steps[steps.length - 1]
    return (
      <p className="flex min-w-0 items-baseline gap-2 text-[12.5px]">
        <span className="shrink-0 font-medium text-ink">{last.stage}</span>
        <span className="min-w-0 truncate text-ink-2" title={last.summary}>{last.summary}</span>
        <span className="ml-auto shrink-0 text-ink-3">Step {Math.min(steps.length + 1, 12)} of 12</span>
      </p>
    )
  }
  // the decision's own reason for anything not approved; for an approval, what happens next (when it gets paid)
  const why = (run.outcome && run.outcome !== 'approved' && run.reason) || whyLine(events) || (run.state === 'error' ? 'Stopped. Nothing was approved.' : '')
  const matched = expect && run.outcome ? run.outcome === expect : null
  return (
    <div className="flex min-w-0 items-center gap-2.5 text-[12.5px]">
      {run.outcome ? <StatusChip outcome={run.outcome} /> : <span className="inline-flex shrink-0 items-center gap-1 font-medium text-ink-2"><Minus size={14} aria-hidden="true" />{run.state === 'error' ? 'Stopped' : 'Not processed'}</span>}
      <span className="min-w-0 truncate text-ink-2" title={why}>{why}</span>
      <span className="ml-auto flex shrink-0 items-center gap-3">
        {run.total ? <span className="font-medium text-ink">{inr(run.total)}</span> : null}
        {matched === true && <span className="inline-flex items-center gap-1 text-vouch"><Check size={14} aria-hidden="true" />As expected</span>}
        {matched === false && <span className="text-hold">Expected: {STATUS[expect]?.label}</span>}
      </span>
    </div>
  )
}

function Row({ it, run, canRun, onProcess, expect, showTests }) {
  const live = run && (run.state === 'starting' || run.state === 'running')
  return (
    <li className="px-4 py-3.5">
      <div className="grid grid-cols-[36px_minmax(0,200px)_minmax(0,1fr)_118px_104px] items-center gap-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-paper text-ink-2">{it.channel === 'email' ? <Mail size={16} /> : it.kind === 'sample' ? <Smartphone size={16} /> : <Upload size={15} />}</span>
        <div className="min-w-0">
          <div className="truncate text-[13.5px] font-medium">{it.title}</div>
          <div className="truncate text-[12.5px] text-ink-2">{it.from}</div>
        </div>
        <div className="min-w-0">
          <div className="truncate text-[13.5px]">{it.subject}</div>
          <div className="flex items-center gap-1.5 truncate text-[12.5px] text-ink-3"><Paperclip size={12} aria-hidden="true" /><span className="truncate">{it.attachment}</span></div>
          {showTests && expect && (
            <div className="mt-0.5 flex items-center gap-1.5 text-[12px] text-ink-3">
              <FlaskConical size={12} aria-hidden="true" /><span className="truncate">{it.caseName ? `Test: ${it.caseName}. ` : 'Test file. '}Expected: {STATUS[expect]?.label}</span>
            </div>
          )}
        </div>
        <span className="text-[12.5px] text-ink-3">{fmtDay(it.received_at)}, {fmtTime(it.received_at)}</span>
        <span className="flex justify-end">
          {!run && canRun && <button className="btn-ink btn-sm" onClick={() => onProcess(it)}>Process</button>}
          {run?.runId && <button className="btn btn-sm" onClick={() => go(`processing/${run.runId}`)}>View steps</button>}
        </span>
      </div>
      {run && (
        <div className="mt-3 grid grid-cols-[36px_minmax(0,1fr)] gap-4">
          <span aria-hidden="true" />
          <div className="min-w-0 space-y-2">
            <StepMap events={run.events} live={live} />
            <StatusLine run={run} expect={showTests ? expect : null} />
          </div>
        </div>
      )}
    </li>
  )
}

function Summary({ runs }) {
  const all = Object.values(runs)
  const active = all.filter((r) => ACTIVE.includes(r.state)).length
  const done = all.filter((r) => r.state === 'done' || r.state === 'error')
  if (!all.length) return null
  if (active) {
    return <p className="text-[13px] text-ink-2">Processing {all.length - active + 1} of {all.length}. You can leave this page; it keeps going.</p>
  }
  const counts = {}
  done.forEach((r) => { const k = r.outcome || 'other'; counts[k] = (counts[k] || 0) + 1 })
  const waiting = (counts.hold || 0) + (counts.security || 0) + (counts.signoff || 0)
  return (
    <p className="flex flex-wrap items-center gap-x-1.5 text-[13px] text-ink-2">
      <span className="font-medium text-ink">Processed {done.length}:</span>
      {Object.entries(counts).map(([k, n], i) => <span key={k}>{n} {k === 'other' ? 'not processed' : (STATUS[k]?.label || k).toLowerCase()}{i < Object.keys(counts).length - 1 ? ',' : ''}</span>)}
      {waiting > 0 && <a href="#/exceptions" className="ml-1 font-medium text-ink underline underline-offset-2">Review exceptions</a>}
    </p>
  )
}

function TestFiles({ pack, showTests, setShowTests }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [])
  return (
    <div ref={ref} className="relative">
      <button className="btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog"><FlaskConical size={15} aria-hidden="true" />Test files</button>
      {open && (
        <div role="dialog" aria-label="Test files" className="absolute right-0 top-[calc(100%+6px)] z-40 w-[460px] rounded-lg border border-line bg-white p-4 shadow-xl">
          <h2 className="text-[14px] font-semibold">Test files</h2>
          <p className="mt-1 text-[12.5px] leading-snug text-ink-2">
            Download a file, upload it here, and compare the result with the one listed. Files 01 to 05 are the invoices in the inbox emails, so uploading one you already processed comes back as a duplicate.
          </p>
          <div className="mt-3 flex justify-between text-[12px] text-ink-3"><span>File and what it tests</span><span>Expected</span></div>
          <ul className="mt-1 divide-y divide-line border-t border-line">
            {pack.map((p) => (
              <li key={p.file} className="flex items-start gap-3 py-2.5">
                <a href={`/api/test-pack/${p.file}`} download className="mt-0.5 text-ink-2 hover:text-ink" aria-label={`Download ${p.file}`}><Download size={15} /></a>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium">{p.file}</div>
                  <div className="text-[12.5px] leading-snug text-ink-2">{p.tests}</div>
                </div>
                <span className="shrink-0"><StatusChip outcome={p.expect} /></span>
              </li>
            ))}
          </ul>
          <div className="mt-1 flex items-center justify-between gap-3 border-t border-line pt-3">
            <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-ink-2">
              <input type="checkbox" checked={showTests} onChange={(e) => setShowTests(e.target.checked)} className="h-3.5 w-3.5 accent-[#17191E]" />
              Show expected results in the inbox
            </label>
            <a href="/api/test-pack.zip" className="btn btn-sm"><Download size={14} aria-hidden="true" />Download all</a>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Inbox() {
  const { docs, waiting, runs, auto, setAuto, enqueue, refresh, canRun } = useRunner()
  const [tab, setTab] = useState('new')
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [drag, setDrag] = useState(false)
  const [pack, setPack] = useState([])
  const [showTests, setShowTestsState] = useState(readShowTests)
  const fileRef = useRef(null)
  useEffect(() => { refresh() }, [refresh])  // pick up anything processed from another page
  useEffect(() => { get('/test-pack').then(setPack).catch(() => {}) }, [])
  const setShowTests = (on) => { try { localStorage.setItem('vouch.showTests', on ? '1' : '0') } catch {} setShowTestsState(on) }

  // Waiting items plus anything run from here this session, so a finished row stays put with its result.
  const rows = [...waiting]
  Object.values(runs).forEach((r) => { if (r.item && !rows.some((w) => w.key === r.item.key)) rows.push(r.item) })
  rows.sort(byArrival)
  const untouched = waiting.filter((w) => !runs[w.key])
  const toProcess = rows.filter((w) => !runs[w.key] || ACTIVE.includes(runs[w.key].state)).length
  const processed = docs.filter((d) => d.run_id)
  const packExpect = Object.fromEntries(pack.map((p) => [p.file, p.expect]))
  const expectOf = (it) => it.expect || packExpect[it.filename] || null  // uploads: only files from the test pack have one

  const addFiles = async (files) => {
    const list = Array.from(files || [])
    if (!list.length) return
    const errs = []
    let added = 0
    for (const f of list) {  // one by one, so they arrive (and get processed) in the order picked
      const big = await tooBig(f)
      if (big) { errs.push(big); continue }
      const fd = new FormData(); fd.append('file', f)
      try { await post('/inbox/upload', fd); added++ } catch (e) { errs.push(`${f.name} could not be uploaded (${e.message}).`) }
    }
    setErr(errs.join(' '))
    setNote(added ? `Added ${added} file${added > 1 ? 's' : ''} to the inbox.${auto ? ' Processing them in the order they arrived.' : ''}` : '')
    setTab('new')
    await refresh()
  }

  const onDragOver = (e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDrag(true) } }
  const onDragLeave = (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDrag(false) }
  const onDrop = (e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files) }

  return (
    <div className="relative max-w-[1180px]" onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
      <PageHead title="Inbox" meta={<span className="inline-flex items-center gap-1.5"><Mail size={14} aria-hidden="true" />ap@sharmacomponents.in</span>}>
        <input ref={fileRef} type="file" multiple className="hidden" accept=".pdf,.jpg,.jpeg,.png,.docx,.eml" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
        {canRun && (
          <span className="inline-flex items-center gap-1.5">
            <Switch on={auto} onChange={setAuto} />
            <InfoTip text="When on, each invoice is processed as soon as it reaches the inbox, including the ones waiting now. Your choice is remembered on this browser." />
          </span>
        )}
        {canRun && !auto && <button className="btn" disabled={!untouched.length} onClick={() => enqueue(untouched)}><Play size={14} aria-hidden="true" />Process all{untouched.length ? ` (${untouched.length})` : ''}</button>}
        <TestFiles pack={pack} showTests={showTests} setShowTests={setShowTests} />
        <button className="btn-ink" onClick={() => fileRef.current.click()}><Upload size={15} aria-hidden="true" />Upload files</button>
      </PageHead>
      {err && <p className="mb-4 rounded-lg border border-alert/30 bg-alert-50 px-3 py-2 text-[13px] text-alert">{err}</p>}
      {note && !err && <p className="mb-4 text-[13px] text-ink-2" role="status">{note}</p>}
      <div className="mb-3"><Segmented value={tab} onChange={setTab} options={[['new', `To process (${toProcess})`], ['done', `Processed (${processed.length})`]]} /></div>

      {tab === 'new' && (
        <>
          {Object.keys(runs).length > 0 && (
            <div className="mb-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2"><Summary runs={runs} /><StepLegend /></div>
          )}
          <ul className="panel divide-y divide-line">
            {rows.length === 0 && <li className="py-8 text-center text-[13px] text-ink-3">Inbox clear. Upload files or drop them here to add more.</li>}
            {rows.map((it) => <Row key={it.key} it={it} run={runs[it.key]} canRun={canRun} onProcess={(x) => enqueue([x])} expect={expectOf(it)} showTests={showTests} />)}
          </ul>
        </>
      )}

      {tab === 'done' && (
        <div className="panel overflow-hidden">
          <table className="tbl">
            <thead><tr><th>Received</th><th>From</th><th>Subject or file</th><th className="w-[170px]">Steps</th><th>Outcome</th></tr></thead>
            <tbody>
              {processed.length === 0 && <tr><td colSpan={5} className="py-8 text-center text-ink-3">Nothing processed yet. Pick something from To process.</td></tr>}
              {processed.map((d) => (
                <tr key={d.doc_id} className="clickable" onClick={() => go(`processing/${d.run_id}`)}>
                  <td className="whitespace-nowrap text-ink-2">{fmtDay(d.received_at)}, {fmtTime(d.received_at)}</td>
                  <td>{d.sender || 'Uploaded'}</td>
                  <td className="max-w-[300px] truncate">{d.subject || d.filename}</td>
                  <td><StageTrack stages={d.stages} /></td>
                  <td>{d.outcome && d.outcome !== 'running' ? <StatusChip outcome={d.outcome} /> : <span className="text-ink-3">{d.run_status === 'error' ? 'Stopped' : d.run_status === 'done' ? (d.classified_as === 'unreadable file' ? 'Could not open' : 'Not an invoice') : 'Processing'}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {drag && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center rounded-xl border-2 border-dashed border-ink-3 bg-white/85 text-[14px] font-medium text-ink">
          Drop files to add them to the inbox
        </div>
      )}
    </div>
  )
}
