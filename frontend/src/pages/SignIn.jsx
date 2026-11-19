import React from 'react'
import { ChevronRight } from 'lucide-react'
import { Logo } from '../ui.jsx'
import { USERS, Avatar, useAuth } from '../auth.jsx'

export default function SignIn() {
  const { signIn } = useAuth()
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-[400px]">
        <div className="mb-8 flex items-center gap-2.5"><Logo size={34} /><span className="text-[22px] font-semibold tracking-tight">Vouch</span></div>
        <div className="panel p-6">
          <h1 className="text-[18px] font-semibold">Sign in to Sharma Components</h1>
          <p className="mt-1 text-[13px] leading-snug text-ink-2">This is a demo with sample data, so there is no password. Start with Ananya to process invoices.</p>
          <ul className="mt-5 divide-y divide-line overflow-hidden rounded-lg border border-line">
            {USERS.map((u) => (
              <li key={u.id}>
                <button onClick={() => signIn(u)} className="flex w-full items-center gap-3 px-3.5 py-3 text-left hover:bg-paper">
                  <Avatar user={u} size={34} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px] font-medium">{u.name}</span>
                    <span className="block truncate text-[12.5px] text-ink-2">{u.role}, {u.email}</span>
                  </span>
                  <ChevronRight size={16} className="text-ink-3" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
        <p className="mt-4 text-center text-[12px] text-ink-3">Neha can release security holds and restore the starting data. Vikram can see everything but change nothing.</p>
      </div>
    </div>
  )
}
