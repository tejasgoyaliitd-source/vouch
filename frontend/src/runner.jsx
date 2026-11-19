import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Flag, Minus } from 'lucide-react'
import { get, post } from './api.js'
import { useAuth } from './auth.jsx'

// Runs inbox items in the background, one at a time and in inbox order, so two invoices against the same PO are
// always checked in the order they arrived. Lives above the pages, so a batch keeps going while you look elsewhere.

export const STAGES = ['Receive', 'Route', 'Read', 'Classify', 'Protect', 'Extract', 'Check extraction', 'Identify vendor',
  'Match PO and receipt', 'Apply rules', 'Decide', 'Act']

const Ctx = createContext(null)
const sampleItem = (s) => ({ key: `s:${s.file}`, kind: 'sample', file: s.file, title: s.vendor, from: s.source,
  subject: s.subject, attachment: s.attachment, channel: s.channel, received_at: s.received_at, caseName: s.name, expect: s.expect })
const docItem = (d) => ({ key: `d:${d.doc_id}`, kind: 'doc', doc_id: d.doc_id, title: 'Uploaded file', from: 'From this desk',
  subject: d.subject || d.filename, attachment: d.subject ? d.filename : `${(d.kind || 'file').toUpperCase()} file`, filename: d.filename,
  channel: 'upload', received_at: d.received_at })
// Oldest first; files uploaded in the same second keep the order they were added in.
export const byArrival = (a, b) => (a.received_at || '').localeCompare(b.received_at || '') || (a.doc_id || 0) - (b.doc_id || 0)
const readAuto = () => { try { return localStorage.getItem('vouch.autoProcess') === '1' } catch { return false } }

export function RunnerProvider({ children }) {
  const { user } = useAuth()
  const canRun = !!user && user.key !== 'auditor'
  const [samples, setSamples] = useState([])
  const [docs, setDocs] = useState([])
  const [runs, setRuns] = useState({})
  const runsRef = useRef({})
  const queue = useRef([])
  const busy = useRef(false)
  const [auto, setAutoState] = useState(readAuto)

  const update = useCallback((key, patch) => {
    runsRef.current = { ...runsRef.current, [key]: { ...runsRef.current[key], ...(typeof patch === 'function' ? patch(runsRef.current[key]) : patch) } }
    setRuns(runsRef.current)
  }, [])

  // Refreshes can overlap; apply only the newest answer, so an older, slower response never overwrites a newer one.
  const seq = useRef(0)
  const refresh = useCallback(() => {
    const n = ++seq.current
    return Promise.all([get('/samples'), get('/documents')])
      .then(([s, d]) => { if (n === seq.current) { setSamples(s); setDocs(d) } }).catch(() => {})
  }, [])
  useEffect(() => { if (user) refresh() }, [user, refresh])

  // Everything in the inbox that has not been processed: emails and photos, plus files uploaded while auto mode was off.
  const waiting = useMemo(() => [
    ...samples.filter((s) => !s.run_id).map(sampleItem),
    ...docs.filter((d) => !d.run_id).map(docItem),
  ].sort(byArrival), [samples, docs])

  const follow = (key, runId) => new Promise((resolve) => {
    const es = new EventSource(`/api/runs/${runId}/events`)
    let closed = false
    const finish = async () => {
      if (closed) return
      closed = true
      es.close()
      for (let i = 0; i < 240; i++) {   // if the stream dropped mid-run, keep checking until the run ends
        try {
          const r = await get(`/runs/${runId}`)
          if (r.status !== 'running' && r.status !== 'queued') {
            const inv = r.invoice
            update(key, { state: r.status === 'error' ? 'error' : 'done', outcome: inv?.outcome, title: inv?.outcome_title, reason: inv?.outcome_reason, invoiceNo: inv?.invoice_no, total: inv?.total, vendor: inv?.vendor_name })
            return resolve()
          }
        } catch {}
        await new Promise((t) => setTimeout(t, 1000))
      }
      update(key, { state: 'error' })
      resolve()
    }
    es.onmessage = (m) => { const e = JSON.parse(m.data); update(key, (cur) => ({ events: [...(cur?.events || []), e] })) }
    es.addEventListener('done', finish)
    es.onerror = finish
  })

  const pump = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    try {
      while (queue.current.length) {
        const it = queue.current.shift()
        update(it.key, { state: 'starting' })
        try {
          const r = await post(it.kind === 'sample' ? `/runs/sample/${encodeURIComponent(it.file)}` : `/runs/document/${it.doc_id}`)
          update(it.key, { state: 'running', runId: r.run_id })
          await follow(it.key, r.run_id)
        } catch (e) {
          update(it.key, { state: 'error', error: e.message })
        }
        refresh()
      }
    } finally {
      busy.current = false
      refresh()
    }
  }, [refresh, update])

  const enqueue = useCallback((items) => {
    const fresh = items.filter((it) => !runsRef.current[it.key])
    if (!fresh.length || !canRun) return
    fresh.forEach((it) => { update(it.key, { item: it, state: 'queued', events: [] }); queue.current.push(it) })
    pump()
  }, [canRun, pump, update])

  // A run still in progress that this page did not start (the tab was reloaded mid-batch, or it was started from
  // Live processing): show it and follow it, so its row stays live instead of vanishing until it ends.
  useEffect(() => {
    const live = new Set(docs.filter((d) => d.run_id && ['running', 'queued'].includes(d.run_status)).map((d) => d.run_id))
    if (!live.size) return
    const found = [
      ...samples.filter((s) => live.has(s.run_id)).map((s) => [sampleItem(s), s.run_id]),
      ...docs.filter((d) => live.has(d.run_id) && !samples.some((s) => s.run_id === d.run_id)).map((d) => [docItem(d), d.run_id]),
    ]
    found.forEach(([it, runId]) => {
      if (runsRef.current[it.key] || Object.values(runsRef.current).some((r) => r.runId === runId)) return
      update(it.key, { item: it, state: 'running', runId, events: [] })
      follow(it.key, runId).then(refresh)
    })
  }, [samples, docs]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto mode: whatever is waiting, and whatever arrives later, is processed without a click.
  const waitingKeys = waiting.map((w) => w.key).join('|')
  useEffect(() => { if (auto && canRun) enqueue(waiting) }, [auto, canRun, waitingKeys]) // eslint-disable-line react-hooks/exhaustive-deps

  const setAuto = (on) => { try { localStorage.setItem('vouch.autoProcess', on ? '1' : '0') } catch {} setAutoState(on) }
  const busyCount = Object.values(runs).filter((r) => ['queued', 'starting', 'running'].includes(r.state)).length
  const value = { samples, docs, waiting, runs, auto, setAuto, enqueue, refresh, canRun, busyCount, active: busyCount > 0 }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useRunner = () => useContext(Ctx)

// A run's 12 steps as a horizontal bar: green passed, amber needs a look, red failed, dark pulsing is the step running now.
export function StageTrack({ events = [], stages, live = false, className = '' }) {
  const by = stages ? Object.fromEntries(stages.map((s, i) => [i + 1, stepKind(s, i + 1)]).filter(([, s]) => s)) : {}
  if (!stages) events.forEach((e) => { if (e.stage_no >= 1 && e.stage_no <= 12) by[e.stage_no] = stepKind(e) })
  const stopped = events.some((e) => e.stage_no === 99)
  const next = live && !stopped ? Object.keys(by).length + 1 : null
  const BAR = { ok: 'bg-vouch', problem: 'bg-alert', look: 'bg-hold', blocked: 'bg-ink-2', fallback: 'bg-ink-3', skipped: 'bg-line' }
  return (
    <div className={`flex gap-[3px] ${className}`} role="img" aria-label={`${Object.keys(by).length} of 12 steps done`}>
      {STAGES.map((name, i) => {
        const s = by[i + 1]
        const cls = s ? BAR[s] : next === i + 1 ? 'bg-ink running-dot' : 'bg-line-2'
        return <span key={name} title={`${i + 1}. ${name}${s ? `: ${KIND_WORD[s]}` : next === i + 1 ? ': running' : ''}`} className={`h-1.5 min-w-0 flex-1 rounded-full ${cls}`} />
      })}
    </div>
  )
}

// Short names for the horizontal step map, in the same order as STAGES.
const SHORT = ['Receive', 'Route', 'Read', 'Classify', 'Protect', 'Extract', 'Check', 'Vendor', 'PO match', 'Rules', 'Decide', 'Act']

/* What a step's mark means. Two very different things must never share a mark:
   - the step ran and found a problem with the invoice ("problem", "look"): Vouch working as intended
   - the step could not run, or ran on a fallback, because of the file or our side ("blocked", "fallback")
   plus "skipped": not needed because an earlier step already settled the outcome. */
export function stepKind(e, stageNo = e?.stage_no) {
  const status = typeof e === 'string' ? e : e?.status
  const summary = typeof e === 'string' ? '' : e?.summary || ''
  if (!status) return null
  if (['ok', 'skip', 'fallback', 'blocked'].includes(status)) return { ok: 'ok', skip: 'skipped', fallback: 'fallback', blocked: 'blocked' }[status]
  if (/^Skipped/.test(summary)) return 'skipped'
  if (stageNo === 5 && status === 'warn') return 'fallback'      // the model call failed; the local parser read alone
  if (stageNo <= 2 && status === 'fail') return 'blocked'        // the file could not be opened or is not a type we read
  return status === 'fail' ? 'problem' : 'look'
}

export const KIND_WORD = { ok: 'Passed', problem: 'Found a problem with the invoice', look: 'Needs a person to look', blocked: 'Could not run',
  fallback: 'Done without the AI model', skipped: 'Skipped, not needed', running: 'Running now', pending: 'Not run yet', notrun: 'Not run' }

// The mark for one step. sm: 14px for the inbox map, lg: 18px for the Live processing timeline.
export function StepIcon({ kind, size = 'sm' }) {
  const box = size === 'lg' ? 'h-[18px] w-[18px]' : 'h-[14px] w-[14px]'
  const ic = size === 'lg' ? 11 : 8.5
  const solid = (bg, icon) => <span className={`flex ${box} items-center justify-center rounded-full ${bg} text-white`}>{icon}</span>
  if (kind === 'ok') return solid('bg-vouch', <Check size={ic + 0.5} strokeWidth={3.5} />)
  if (kind === 'problem') return solid('bg-alert', <Flag size={ic - 1} strokeWidth={3} fill="currentColor" />)
  if (kind === 'look') return solid('bg-hold', <Flag size={ic - 1} strokeWidth={3} fill="currentColor" />)
  if (kind === 'blocked') return solid('bg-ink-2', <Minus size={ic + 0.5} strokeWidth={4} />)
  if (kind === 'fallback') return <span className={`flex ${box} items-center justify-center rounded-full border-2 border-ink-3 bg-white text-ink-3`}><Check size={ic - 1} strokeWidth={4} /></span>
  if (kind === 'running') return <span className={`running-dot block ${box} rounded-full ${size === 'lg' ? 'border-[5px]' : 'border-[4px]'} border-ink bg-white`} />
  if (kind === 'skipped' || kind === 'notrun') return <span className={`block ${box} rounded-full border-2 border-dashed border-line-2 bg-white`} />
  return <span className={`block ${box} rounded-full border-2 border-line-2 bg-white`} />
}

// Each step's kind for a run: finished steps from their events; after a crash, the next step "could not run"
// and the rest "not run"; while live, the next step is running.
export function stepKinds(events = [], live = false) {
  const by = {}
  events.forEach((e) => { if (e.stage_no >= 1 && e.stage_no <= 12) by[e.stage_no] = e })
  const crashed = events.some((e) => e.stage_no === 99)
  const done = Object.keys(by).length
  const stoppedEarly = !live && done > 0 && done < 12
  return STAGES.map((_, i) => {
    const e = by[i + 1]
    if (e) return stepKind(e)
    if (crashed) return i === done ? 'blocked' : 'notrun'
    if (live) return i === done ? 'running' : 'pending'
    return stoppedEarly ? 'notrun' : 'pending'
  })
}

// One-line key for the marks, shown once above a list of step maps.
export function StepLegend({ className = '' }) {
  const items = [['ok', 'Passed'], ['problem', 'Problem found in the invoice'], ['blocked', 'Could not run'], ['skipped', 'Skipped']]
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-3 ${className}`}>
      {items.map(([k, label]) => <span key={k} className="inline-flex items-center gap-1.5"><StepIcon kind={k} />{label}</span>)}
    </div>
  )
}

// The 12 steps as a labelled horizontal map: the inbox row's version of the vertical timeline on Live processing.
export function StepMap({ events = [], live = false }) {
  const kinds = stepKinds(events, live)
  const by = {}
  events.forEach((e) => { if (e.stage_no >= 1 && e.stage_no <= 12) by[e.stage_no] = e })
  return (
    <ol className="grid grid-cols-12" aria-label={`${Object.keys(by).length} of 12 steps done`}>
      {STAGES.map((name, i) => {
        const e = by[i + 1]
        const k = kinds[i]
        const last = i === STAGES.length - 1
        return (
          <li key={name} className="relative min-w-0 pr-1" title={`${i + 1}. ${name}: ${KIND_WORD[k]}${e ? `. ${e.summary}` : ''}`}>
            {!last && <span className={`absolute left-[15px] right-[1px] top-[6.5px] h-px ${e ? 'bg-ink-3' : 'bg-line-2'}`} aria-hidden="true" />}
            <span className="relative block"><StepIcon kind={k} /></span>
            <span className={`mt-1.5 block truncate text-[11.5px] leading-tight ${k === 'running' ? 'font-medium text-ink' : e && k !== 'skipped' ? 'text-ink-2' : 'text-ink-3'}`}>{SHORT[i]}</span>
          </li>
        )
      })}
    </ol>
  )
}

// One line on why a finished run ended where it did: the first check that failed, else the first that needs a look,
// else what was done (for an approval, when it gets paid).
export function whyLine(events = []) {
  const steps = events.filter((e) => e.stage_no >= 1 && e.stage_no <= 12)
  const err = events.find((e) => e.stage_no === 99)
  if (err) return err.summary
  const pick = steps.find((e) => e.status === 'fail' && e.stage_no !== 11) || steps.find((e) => e.status === 'warn' && e.stage_no !== 11)
  return (pick || steps.find((e) => e.stage_no === 12) || steps[steps.length - 1])?.summary || ''
}

export function currentStep(events = []) {
  const err = events.find((e) => e.stage_no === 99)
  if (err) return 'Stopped'
  const done = events.filter((e) => e.stage_no >= 1 && e.stage_no <= 12).length
  return done >= 12 ? 'Deciding' : STAGES[done]
}
