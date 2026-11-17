import React, { useEffect, useRef, useState } from 'react'
import { LayoutGrid, Inbox as InboxIcon, Activity, CircleAlert, FileText, Building2, ScrollText, Lock, LogOut, ChevronsUpDown, RotateCcw, UserRound } from 'lucide-react'
import Overview from './pages/Overview.jsx'
import Inbox from './pages/Inbox.jsx'
import Processing from './pages/Processing.jsx'
import Exceptions from './pages/Exceptions.jsx'
import Invoices from './pages/Invoices.jsx'
import Invoice from './pages/Invoice.jsx'
import Vendors from './pages/Vendors.jsx'
import Audit from './pages/Audit.jsx'
import SignIn from './pages/SignIn.jsx'
import { AuthProvider, useAuth, Avatar, USERS } from './auth.jsx'
import { Logo } from './ui.jsx'
import { get, post } from './api.js'

const NAV = [
  ['overview', 'Overview', LayoutGrid], ['inbox', 'Inbox', InboxIcon], ['processing', 'Live processing', Activity],
  ['exceptions', 'Exceptions', CircleAlert], ['invoices', 'Invoices', FileText], ['vendors', 'Vendors and POs', Building2],
  ['audit', 'Audit trail', ScrollText],
]

function useRoute() {
  const [hash, setHash] = useState(window.location.hash || '#/overview')
  useEffect(() => {
    const on = () => setHash(window.location.hash || '#/overview')
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash.replace(/^#\//, '').split('/')
}
export const go = (path) => { window.location.hash = '#/' + path }

function ProfileMenu() {
  const { user, signIn, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const restore = async () => { if (confirm('Restore the starting data? Processed invoices and decisions made today are cleared.')) { await post('/demo/reset'); window.location.hash = '#/overview'; window.location.reload() } }
  return (
    <div ref={ref} className="relative">
      {open && (
        <div className="absolute bottom-[calc(100%+6px)] left-0 right-0 z-40 rounded-lg border border-line bg-white p-1.5 shadow-xl">
          <div className="px-2.5 py-2">
            <div className="text-[13px] font-medium">{user.name}</div>
            <div className="truncate text-[12px] text-ink-2">{user.email}</div>
          </div>
          <div className="my-1 border-t border-line" />
          <div className="px-2.5 pb-1 pt-1.5 text-[12px] text-ink-3">Switch account</div>
          {USERS.filter((u) => u.id !== user.id).map((u) => (
            <button key={u.id} onClick={() => { signIn(u); setOpen(false) }} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] hover:bg-paper">
              <Avatar user={u} size={22} />{u.name}<span className="ml-auto text-[12px] text-ink-3">{u.role}</span>
            </button>
          ))}
          <div className="my-1 border-t border-line" />
          {user.key === 'ap_manager' && (
            <button onClick={restore} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] hover:bg-paper"><RotateCcw size={15} className="text-ink-2" />Restore starting data</button>
          )}
          <button onClick={signOut} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] hover:bg-paper"><LogOut size={15} className="text-ink-2" />Sign out</button>
        </div>
      )}
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-paper" aria-haspopup="menu" aria-expanded={open}>
        <Avatar user={user} size={30} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium">{user.name}</span>
          <span className="block truncate text-[12px] text-ink-2">{user.role}</span>
        </span>
        <ChevronsUpDown size={15} className="text-ink-3" aria-hidden="true" />
      </button>
    </div>
  )
}

function PrivacyStatus() {
  const [s, setS] = useState(null)
  useEffect(() => { get('/status').then(setS).catch(() => {}) }, [])
  const name = s?.provider === 'gemini' ? 'Gemini' : s?.provider === 'claude' ? 'Claude' : null
  return (
    <div className="group relative mx-1 mb-2" tabIndex={0}>
      <div className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-2 text-[12.5px] text-ink-2">
        <Lock size={14} className="text-vouch" aria-hidden="true" />
        <span>{name ? `${name}, masked text only` : 'Reading on device'}</span>
        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-vouch" aria-hidden="true" />
      </div>
      <div role="tooltip" className="pointer-events-none absolute bottom-[calc(100%+6px)] left-0 z-30 w-64 rounded-md bg-ink px-3 py-2.5 text-[12px] leading-snug text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus:opacity-100">
        {name
          ? `${name} (${s.model}) reads invoice fields from the page text after bank details, PAN, phone numbers and emails are masked. A local parser reads the same page; where the two disagree, a person confirms. Decisions are made by rules, never by the model.`
          : 'Invoices are read with OCR on this server. No AI model is connected, so no document text leaves your network.'}
      </div>
    </div>
  )
}

function Shell() {
  const { user } = useAuth()
  const [page, arg] = useRoute()
  const [open, setOpen] = useState(0)
  useEffect(() => {
    if (!user) return
    const load = () => get('/queue').then((q) => setOpen(q.length)).catch(() => {})
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [user])
  if (!user) return <SignIn />
  const active = page === 'invoice' ? 'invoices' : page

  return (
    <div className="grid min-h-screen grid-cols-[236px_minmax(0,1fr)]">
      <aside className="sticky top-0 flex h-screen flex-col border-r border-line bg-white px-3 pb-3 pt-4">
        <a href="#/overview" className="mb-6 flex items-center gap-2 px-2"><Logo size={28} /><span className="text-[18px] font-semibold tracking-tight">Vouch</span></a>
        <nav className="space-y-0.5" aria-label="Main">
          {NAV.map(([k, label, Icon]) => (
            <a key={k} href={`#/${k}`} aria-current={active === k ? 'page' : undefined}
              className={`flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13.5px] ${active === k ? 'bg-paper font-medium text-ink' : 'text-ink-2 hover:bg-paper hover:text-ink'}`}>
              <Icon size={17} strokeWidth={active === k ? 2.2 : 1.8} aria-hidden="true" />
              {label}
              {k === 'exceptions' && open > 0 && <span className="ml-auto rounded-full bg-hold-50 px-1.5 text-[11.5px] font-semibold text-hold">{open}</span>}
            </a>
          ))}
        </nav>
        <div className="mt-auto">
          <PrivacyStatus />
          <ProfileMenu />
        </div>
      </aside>
      <main className="min-w-0 px-8 py-7">
        {page === 'overview' && <Overview />}
        {page === 'inbox' && <Inbox />}
        {page === 'processing' && <Processing runId={arg} />}
        {page === 'exceptions' && <Exceptions />}
        {page === 'invoices' && <Invoices />}
        {page === 'invoice' && <Invoice id={arg} />}
        {page === 'vendors' && <Vendors />}
        {page === 'audit' && <Audit />}
      </main>
    </div>
  )
}

export default function App() {
  return <AuthProvider><Shell /></AuthProvider>
}
