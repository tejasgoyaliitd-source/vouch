import React, { createContext, useContext, useState } from 'react'

export const USERS = [
  { id: 'ananya', name: 'Ananya Rao', role: 'AP specialist', key: 'ap', email: 'ananya.rao@sharmacomponents.in' },
  { id: 'neha', name: 'Neha Kapoor', role: 'AP manager', key: 'ap_manager', email: 'neha.kapoor@sharmacomponents.in' },
  { id: 'vikram', name: 'Vikram Shah', role: 'Internal audit', key: 'auditor', email: 'vikram.shah@sharmacomponents.in' },
]
export const initials = (name) => name.split(' ').map((p) => p[0]).join('').slice(0, 2)

const Ctx = createContext(null)
const read = () => { try { return USERS.find((u) => u.id === localStorage.getItem('vouch.user')) || null } catch { return null } }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(read)
  const signIn = (u) => { try { localStorage.setItem('vouch.user', u.id) } catch {} setUser(u) }
  const signOut = () => { try { localStorage.removeItem('vouch.user') } catch {} setUser(null); window.location.hash = '#/overview' }
  return <Ctx.Provider value={{ user, signIn, signOut }}>{children}</Ctx.Provider>
}
export const useAuth = () => useContext(Ctx)

export function Avatar({ user, size = 32 }) {
  const tone = { ananya: 'bg-review-50 text-review', neha: 'bg-vouch-50 text-vouch', vikram: 'bg-reject-50 text-reject' }[user.id]
  return <span className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${tone}`} style={{ width: size, height: size, fontSize: size * 0.38 }}>{initials(user.name)}</span>
}
