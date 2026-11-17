import React, { useEffect, useState } from 'react'
import { Check, X, AlertTriangle, Copy, Mail, Send, ChevronDown, Phone, ExternalLink } from 'lucide-react'
import { get, post, postJson } from '../api.js'
import { PageHead, Segmented, StatusChip, STATUS, inr, ago } from '../ui.jsx'
import { useAuth } from '../auth.jsx'
import { go } from '../App.jsx'

const OWNER = { ap: 'AP desk', procurement: 'Procurement', stores: 'Stores', vendor: 'Vendor', ap_manager: 'AP manager' }
const OWNER_FULL = { ap: 'the AP desk', procurement: 'Procurement (R. Mehta)', stores: 'Stores (S. Iyer)', vendor: 'the vendor', ap_manager: 'the AP manager' }
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)

export function Draft({ task, onSent }) {
  const [body, setBody] = useState(task.draft_body || '')
  const [copied, setCopied] = useState(false)
  useEffect(() => setBody(task.draft_body || ''), [task.task_id])
  const copy = async () => { try { await navigator.clipboard.writeText(`To: ${task.draft_to}\nSubject: ${task.draft_subject}\n\n${body}`); setCopied(true); setTimeout(() => setCopied(false), 1600) } catch {} }
  const mailto = `mailto:${task.draft_to}?subject=${encodeURIComponent(task.draft_subject || '')}&body=${encodeURIComponent(body)}`
  return (
    <div className="rounded-lg border border-line">
      <div className="grid grid-cols-[64px_1fr] gap-y-1.5 border-b border-line px-3.5 py-3 text-[13px]">
        <span className="text-ink-3">To</span><span className="truncate">{task.draft_to}{task.owner_role === 'vendor' && <span className="ml-2 text-[12px] text-ink-3">from the vendor master</span>}</span>
        <span className="text-ink-3">Subject</span><span className="truncate">{task.draft_subject}</span>
      </div>
      <textarea aria-label="Message" className="block h-56 w-full resize-y bg-white px-3.5 py-3 text-[13.5px] leading-relaxed outline-none" value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="flex flex-wrap items-center gap-2 border-t border-line px-3.5 py-2.5">
        <button className="btn btn-sm" onClick={copy}><Copy size={14} />{copied ? 'Copied' : 'Copy'}</button>
        <a className="btn btn-sm" href={mailto}><Mail size={14} />Open in email</a>
        <button className="btn-ink btn-sm" onClick={async () => { await post(`/tasks/${task.task_id}/sent`); onSent() }}><Send size={14} />Mark as sent</button>
      </div>
    </div>
  )
}

function Detail({ task, onChanged }) {
  const { user } = useAuth()
  const [inv, setInv] = useState(null)
  const [showPassed, setShowPassed] = useState(false)
  const [showDraft, setShowDraft] = useState(false)
  useEffect(() => { setInv(null); setShowDraft(false); setShowPassed(false); get(`/invoices/${task.invoice_id}`).then(setInv) }, [task.task_id])
  if (!inv) return <div className="panel h-[520px] animate-pulse" />
  const found = inv.rules.filter((r) => r.outcome === 'fail' || r.outcome === 'warn')
  const passed = inv.rules.filter((r) => r.outcome === 'pass')
  const managerOnly = task.kind === 'call' || task.kind === 'signoff'
  const canAct = user.key !== 'auditor' && (!managerOnly || user.key === 'ap_manager')
  const resolve = async (action) => { await postJson(`/tasks/${task.task_id}/resolve`, { action, by: user.name }); onChanged() }
  const others = inv.tasks.filter((t) => t.task_id !== task.task_id && t.status !== 'done')
  const labels = task.kind === 'call' ? ['Confirmed by phone, approve', 'Not confirmed, reject'] : task.kind === 'signoff' ? ['Sign off and approve', 'Reject'] : [others.length ? 'Resolved' : 'Resolved, approve', 'Reject invoice']

  return (
    <section className="panel" aria-label="Exception detail">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <div className="flex flex-wrap items-center gap-2"><span className="id text-[14px] font-medium">{inv.invoice_no}</span><StatusChip outcome={inv.outcome} /></div>
          <div className="mt-1 text-[16px] font-semibold">{inv.vendor_name} <span className="font-normal text-ink-2">{inr(inv.total)}</span></div>
        </div>
        <button className="btn btn-sm" onClick={() => go(`invoice/${inv.invoice_id}`)}><ExternalLink size={14} />Open invoice</button>
      </header>

      <div className="space-y-5 px-5 py-4">
        <div>
          <h3 className="mb-2 text-[13px] font-semibold">What was found</h3>
          <ul className="space-y-2">
            {found.map((r) => (
              <li key={r.rule_id} className="grid grid-cols-[18px_1fr] gap-2 text-[13.5px] leading-relaxed">
                {r.outcome === 'fail' ? <X size={16} className="mt-0.5 text-alert" /> : <AlertTriangle size={15} className="mt-0.5 text-hold" />}
                <span><span className="font-medium">{r.title}.</span> <span className="text-ink-2">{r.detail}</span></span>
              </li>
            ))}
          </ul>
        </div>

        {passed.length > 0 && (
          <div>
            <button className="flex items-center gap-1.5 text-[13px] font-semibold" onClick={() => setShowPassed((s) => !s)} aria-expanded={showPassed}>
              Already checked, {passed.length} passed<ChevronDown size={14} className={`text-ink-3 transition ${showPassed ? 'rotate-180' : ''}`} />
            </button>
            {showPassed && (
              <ul className="mt-2 space-y-1">
                {passed.map((r) => <li key={r.rule_id} className="grid grid-cols-[18px_1fr] gap-2 text-[12.5px] text-ink-2"><Check size={14} className="mt-0.5 text-vouch" /><span><span className="text-ink">{r.title}.</span> {r.detail}</span></li>)}
              </ul>
            )}
          </div>
        )}

        <div className="rounded-lg bg-paper px-4 py-3.5">
          <div className="mb-1 flex items-center gap-1.5 text-[12.5px] font-medium text-ink-2">{task.kind === 'call' && <Phone size={13} />}Question for {OWNER_FULL[task.owner_role]}</div>
          <p className="text-[14px] leading-relaxed">{task.ask}</p>
          {task.status === 'sent' && <p className="mt-1.5 text-[12.5px] text-ink-3">Message sent. Waiting for a reply.</p>}
        </div>

        {task.draft_body && (
          <div>
            <button className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold" onClick={() => setShowDraft((s) => !s)} aria-expanded={showDraft}>
              Drafted message to {OWNER[task.owner_role].toLowerCase()}<ChevronDown size={14} className={`text-ink-3 transition ${showDraft ? 'rotate-180' : ''}`} />
            </button>
            {showDraft && <Draft task={task} onSent={onChanged} />}
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
        {canAct ? (
          <>
            <button className="btn-ink" onClick={() => resolve('approve')}><Check size={15} />{labels[0]}</button>
            <button className="btn" onClick={() => resolve('reject')}><X size={15} />{labels[1]}</button>
            {others.length > 0 && <span className="text-[13px] text-ink-3">Stays on hold until {others.map((t) => OWNER_FULL[t.owner_role]).join(' and ')} {others.length > 1 ? 'reply' : 'replies'}</span>}
          </>
        ) : (
          <span className="text-[13px] text-ink-3">{user.key === 'auditor' ? 'View only for internal audit' : 'Needs an AP manager to decide'}</span>
        )}
      </footer>
    </section>
  )
}

export default function Exceptions() {
  const { user } = useAuth()
  const [tasks, setTasks] = useState(null)
  const [filter, setFilter] = useState(user.key === 'auditor' ? 'all' : 'mine')
  const [sel, setSel] = useState(null)
  const load = () => get('/queue').then((t) => { setTasks(t); setSel((s) => (s && t.find((x) => x.task_id === s) ? s : null)) })
  useEffect(() => { load() }, [])
  if (!tasks) return null
  const mineKey = user.key === 'ap_manager' ? 'ap_manager' : 'ap'
  const shown = tasks.filter((t) => filter === 'all' || (filter === 'mine' ? t.owner_role === mineKey : t.owner_role === filter))
  const count = (k) => tasks.filter((t) => t.owner_role === k).length
  const current = shown.find((t) => t.task_id === sel) || shown[0]

  return (
    <div className="max-w-[1320px]">
      <PageHead title="Exceptions">
        <Segmented value={filter} onChange={setFilter} options={[
          ...(user.key !== 'auditor' ? [['mine', `Mine (${count(mineKey)})`]] : []), ['all', `All (${tasks.length})`],
          ['procurement', `Procurement (${count('procurement')})`], ['stores', `Stores (${count('stores')})`], ['vendor', `Vendors (${count('vendor')})`],
          ...(user.key !== 'ap_manager' ? [['ap_manager', `AP manager (${count('ap_manager')})`]] : []),
        ]} />
      </PageHead>
      {shown.length === 0 ? (
        <div className="panel flex h-64 flex-col items-center justify-center gap-1 text-center">
          <Check size={22} className="text-vouch" /><div className="text-[14px] font-medium">Nothing waiting here</div><div className="text-[13px] text-ink-2">Exceptions assigned to this group appear as invoices are processed.</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
          <ul className="panel h-fit divide-y divide-line overflow-hidden" aria-label="Exceptions">
            {shown.map((t) => {
              const on = current?.task_id === t.task_id
              return (
                <li key={t.task_id}>
                  <button onClick={() => setSel(t.task_id)} className={`grid w-full grid-cols-[8px_1fr] gap-3 px-4 py-3 text-left ${on ? 'bg-paper' : 'hover:bg-[#FAFAF8]'}`} aria-current={on}>
                    <span className={`mt-1.5 h-2 w-2 rounded-full ${STATUS[t.outcome]?.dot || 'bg-ink-3'}`} aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="flex items-baseline justify-between gap-2"><span className="truncate text-[13.5px] font-medium">{t.vendor_name}</span><span className="shrink-0 text-[13px]">{inr(t.total)}</span></span>
                      <span className="mt-0.5 flex items-baseline justify-between gap-2 text-[12.5px] text-ink-2">
                        <span className="truncate">{cap(t.type)}, {OWNER[t.owner_role].toLowerCase()}</span>
                        <span className="shrink-0 text-ink-3">{t.source === 'pipeline' ? 'New' : ago(t.created_at)}</span>
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
          {current && <Detail task={current} onChanged={load} />}
        </div>
      )}
    </div>
  )
}
