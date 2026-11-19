import React, { useEffect, useRef, useState } from 'react'
import { Upload, Mail, Smartphone, ChevronDown, Check, Flag, Minus, EyeOff, Eye, RotateCw } from 'lucide-react'
import { get, post, tooBig } from '../api.js'
import { DecisionCard, DocViewer, PageHead, StatusChip, inr } from '../ui.jsx'
import { go } from '../App.jsx'
import { StepIcon, StepLegend, stepKinds } from '../runner.jsx'

const STAGES = ['Receive', 'Route', 'Read', 'Classify', 'Protect', 'Extract', 'Check extraction', 'Identify vendor',
  'Match PO and receipt', 'Apply rules', 'Decide', 'Act']
// A word next to the step name for anything that is not a plain pass, so a flag (the invoice has a problem) is never
// mistaken for a step that could not run.
const TAG = { problem: ['Problem found', 'text-alert'], look: ['Needs a look', 'text-hold'], blocked: ['Could not run', 'text-ink-2'],
  fallback: ['Done without the AI model', 'text-ink-3'], skipped: ['Skipped', 'text-ink-3'], notrun: ['Not run', 'text-ink-3'] }
const ROUTE = { einvoice: 'Signed e-invoice QR and text layer', text: 'PDF text layer', scan: 'Scan, read with OCR', photo: 'Photo, straightened and read with OCR', docx: 'Word document' }

function Detail({ d }) {
  if (!d) return null
  if (Array.isArray(d)) {
    return (
      <ul className="space-y-1.5">
        {d.map((r) => (
          <li key={r.rule} className="grid grid-cols-[18px_1fr] gap-2 text-[12.5px]">
            {r.outcome === 'pass' ? <Check size={15} className="mt-0.5 text-vouch" /> : r.outcome === 'fail' ? <Flag size={13} className="mt-1 text-alert" fill="currentColor" /> : r.outcome === 'warn' ? <Flag size={13} className="mt-1 text-hold" fill="currentColor" /> : <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-ink-3" />}
            <span><span className="font-medium text-ink">{r.title}.</span> <span className="text-ink-2">{r.detail}</span></span>
          </li>
        ))}
      </ul>
    )
  }
  if (d.rows) return <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-md bg-paper p-3 font-mono text-[11.5px] leading-relaxed text-ink-2">{d.rows.slice(0, 32).join('\n')}</pre>
  if (d.masked_text) return <Masked text={d.masked_text} />
  if (d.fields) return <div className="grid grid-cols-2 gap-x-5 gap-y-1 text-[12.5px]">{Object.entries(d.fields).map(([k, v]) => <div key={k} className="truncate"><span className="text-ink-3">{k.replace(/_/g, ' ')}</span> {String(v[0])}</div>)}</div>
  return <div className="space-y-0.5 text-[12.5px] text-ink-2">{Object.entries(d).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length)).map(([k, v]) => <div key={k}><span className="text-ink-3">{k.replace(/_/g, ' ')}</span> {Array.isArray(v) ? v.join(', ') : String(v)}</div>)}</div>
}

function Masked({ text }) {
  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-ink p-3 font-mono text-[11.5px] leading-relaxed text-white/80">
      {text.split(/(\[[A-Z]+_\d+\])/).map((p, i) => (/^\[[A-Z]+_\d+\]$/.test(p) ? <span key={i} className="rounded bg-white/15 px-1 text-[#9BE3C1]">{p}</span> : p))}
    </pre>
  )
}

function Picker({ samples, onPick, onUpload, busy }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {samples.map((s) => (
        <button key={s.file} onClick={() => onPick(s.file)} disabled={!!busy}
          className="group panel overflow-hidden text-left transition hover:border-ink-3 disabled:opacity-60">
          <div className="h-28 overflow-hidden border-b border-line bg-paper">
            <img src={`/api/samples/${s.file}/thumb`} alt="" className="w-full object-cover object-top transition group-hover:scale-[1.02]" />
          </div>
          <div className="p-3">
            <div className="text-[13.5px] font-medium leading-snug">{s.name}</div>
            <div className="mt-0.5 truncate text-[12.5px] text-ink-2">{s.vendor}</div>
            <div className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-3">{s.channel === 'email' ? <Mail size={13} /> : <Smartphone size={13} />}{s.format}</div>
          </div>
        </button>
      ))}
      <button onClick={onUpload} className="flex min-h-[200px] flex-col items-center justify-center gap-2 rounded-[10px] border border-dashed border-line-2 bg-white/50 text-center text-[13px] text-ink-2 transition hover:border-ink-3 hover:text-ink">
        <Upload size={20} aria-hidden="true" />Upload your own<span className="text-[12px] text-ink-3">PDF, scan, photo, Word or .eml</span>
      </button>
    </div>
  )
}

export default function Processing({ runId }) {
  const [samples, setSamples] = useState([])
  const [events, setEvents] = useState([])
  const [run, setRun] = useState(null)
  const [open, setOpen] = useState({})
  const [live, setLive] = useState(false)
  const [busy, setBusy] = useState(null)
  const [masked, setMasked] = useState(false)
  const [err, setErr] = useState('')
  const fileRef = useRef(null)

  useEffect(() => { get('/samples').then(setSamples).catch(() => setErr('The processing service is not reachable. Check that the API is running.')) }, [])
  useEffect(() => {
    if (!runId) return
    setEvents([]); setRun(null); setOpen({}); setLive(true); setBusy(null); setMasked(false)
    const es = new EventSource(`/api/runs/${runId}/events`)
    es.onmessage = (m) => {
      const e = JSON.parse(m.data)
      setEvents((p) => [...p, e])
      if (e.stage_no >= 6) get(`/runs/${runId}`).then(setRun).catch(() => {})
    }
    es.addEventListener('done', () => { es.close(); setLive(false); get(`/runs/${runId}`).then(setRun) })
    es.onerror = () => { es.close(); setLive(false) }
    get(`/runs/${runId}`).then(setRun).catch(() => {})
    return () => es.close()
  }, [runId])

  const pick = async (file) => { setBusy(file); setErr(''); try { const r = await post(`/runs/sample/${encodeURIComponent(file)}`); go(`processing/${r.run_id}`) } catch (e) { setErr('Could not start: ' + e.message); setBusy(null) } }
  const upload = async (f) => { if (!f) return; const big = await tooBig(f); if (big) { setErr(big); return } const fd = new FormData(); fd.append('file', f); try { const r = await post('/runs/upload', fd); go(`processing/${r.run_id}`) } catch (e) { setErr('Upload failed: ' + e.message) } }

  const inv = run?.invoice, doc = run?.document
  const t0 = events[0] ? new Date(events[0].ts).getTime() : null
  const protect = events.find((e) => e.stage === 'Protect')?.detail?.masked_text
  const errorEv = events.find((e) => e.stage_no === 99)
  const kinds = stepKinds(events, live)

  return (
    <div className="max-w-[1320px]">
      <PageHead title="Live processing">
        <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.eml" className="hidden" onChange={(e) => upload(e.target.files[0])} />
        {runId && <button className="btn" onClick={() => go('processing')}><RotateCw size={15} aria-hidden="true" />Process another</button>}
        <button className="btn-ink" onClick={() => fileRef.current.click()}><Upload size={15} aria-hidden="true" />Upload a file</button>
      </PageHead>
      {err && <p className="mb-4 rounded-lg border border-alert/30 bg-alert-50 px-3 py-2 text-[13px] text-alert">{err}</p>}

      {!runId && <Picker samples={samples} onPick={pick} onUpload={() => fileRef.current.click()} busy={busy} />}

      {runId && (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.08fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="id text-[15px] font-medium text-ink">{inv?.invoice_no || doc?.filename || 'Reading'}</span>
              {inv?.vendor_name && <span className="text-[14px] text-ink">{inv.vendor_name}</span>}
              {inv?.total ? <span className="text-[14px] font-medium">{inr(inv.total)}</span> : null}
              {inv && <StatusChip outcome={inv.outcome} />}
              <span className="w-full text-[12.5px] text-ink-3">{doc?.channel === 'email' ? `Email from ${doc.sender}` : 'Uploaded'}{run?.route ? `, ${ROUTE[run.route] || run.route}` : ''}</span>
            </div>
            <DecisionCard inv={inv} actions={inv && inv.outcome !== 'running' && <>
              <button className="btn" onClick={() => go(`invoice/${inv.invoice_id}`)}>Open invoice</button>
              {['hold', 'security', 'signoff'].includes(inv.outcome) && <button className="btn-ink" onClick={() => go('exceptions')}>Go to exception</button>}
            </>} />
            {errorEv && <p className="flex items-start gap-2 rounded-lg border border-line-2 bg-white px-3 py-2 text-[13px] text-ink"><Minus size={15} className="mt-0.5 shrink-0 text-ink-2" aria-hidden="true" />{errorEv.summary}</p>}

            <section className="panel py-2" aria-label="Steps">
              <StepLegend className="border-b border-line px-4 pb-2.5 pt-1.5" />
              <ol>
                {STAGES.map((name, i) => {
                  const e = events.find((x) => x.stage_no === i + 1)
                  const state = kinds[i]
                  const last = i === STAGES.length - 1
                  return (
                    <li key={name} className="relative grid grid-cols-[28px_1fr] px-4">
                      {!last && <span className={`absolute left-[29px] top-[26px] h-[calc(100%-14px)] w-px ${e ? 'bg-line-2' : 'bg-line'}`} aria-hidden="true" />}
                      <span className="relative pt-[11px]"><StepIcon kind={state} size="lg" /></span>
                      <div className="min-w-0 py-2">
                        <button className="flex w-full items-baseline gap-3 text-left" onClick={() => e?.detail && setOpen((o) => ({ ...o, [i]: !o[i] }))} aria-expanded={!!open[i]}>
                          <span className={`text-[13.5px] font-medium ${(e && state !== 'skipped') || state === 'running' ? 'text-ink' : 'text-ink-3'}`}>{name}</span>
                          {TAG[state] && <span className={`text-[12px] font-medium ${TAG[state][1]}`}>{TAG[state][0]}</span>}
                          {e?.detail && <ChevronDown size={14} className={`text-ink-3 transition ${open[i] ? 'rotate-180' : ''}`} aria-hidden="true" />}
                          {e && t0 && <span className="ml-auto text-[12px] text-ink-3">{((new Date(e.ts).getTime() - t0) / 1000).toFixed(0)} s</span>}
                        </button>
                        {e && <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">{e.summary}</p>}
                        {state === 'running' && <p className="mt-0.5 text-[13px] text-ink-3">Working</p>}
                        {open[i] && e?.detail && <div className="mb-1 mt-2.5"><Detail d={e.detail} /></div>}
                      </div>
                    </li>
                  )
                })}
              </ol>
            </section>
          </div>

          <section className="panel h-fit p-4" aria-label="Document">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="text-[14px] font-semibold">Document</h2>
              {protect && (
                <button className="btn btn-sm" onClick={() => setMasked((m) => !m)}>{masked ? <EyeOff size={14} /> : <Eye size={14} />}{masked ? 'Show page' : 'What a model would see'}</button>
              )}
            </div>
            {masked && protect ? <Masked text={protect} /> : <DocViewer docId={inv ? run.doc_id : null} fields={inv?.fields || []} />}
          </section>
        </div>
      )}
    </div>
  )
}
