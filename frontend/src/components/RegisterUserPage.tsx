import { useEffect, useState } from 'react'
import type { UserRecord } from '../types'
import { listUsers, createUser, deactivateUser, reactivateUser, deleteUser } from '../lib/api'

export function RegisterUserPage() {
  const [users, setUsers] = useState<UserRecord[]>([])
  const [loadingUsers, setLoadingUsers] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccess, setFormSuccess] = useState<string | null>(null)

  const fetchUsers = async () => {
    setLoadingUsers(true)
    setFetchError(null)
    try {
      const data = await listUsers()
      setUsers(data)
    } catch (err: any) {
      setFetchError(err.message)
    } finally {
      setLoadingUsers(false)
    }
  }

  useEffect(() => { fetchUsers() }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setFormSuccess(null)
    setSubmitting(true)
    try {
      await createUser({ username, password, full_name: fullName || undefined, role })
      setFormSuccess(`User "${username}" created successfully.`)
      setUsername('')
      setPassword('')
      setFullName('')
      setRole('user')
      await fetchUsers()
    } catch (err: any) {
      let msg = err.message
      try {
        const detail = JSON.parse(msg.split(': ').slice(1).join(': '))
        if (detail?.detail) msg = detail.detail
      } catch { /* ignore */ }
      setFormError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeactivate = async (u: UserRecord) => {
    if (!confirm(`Deactivate "${u.username}"? They won't be able to log in.`)) return
    try {
      await deactivateUser(u.username)
      await fetchUsers()
    } catch (err: any) { alert(err.message) }
  }

  const handleReactivate = async (u: UserRecord) => {
    try {
      await reactivateUser(u.username)
      await fetchUsers()
    } catch (err: any) { alert(err.message) }
  }

  const handleDelete = async (u: UserRecord) => {
    if (!confirm(`Permanently delete "${u.username}"? This cannot be undone.`)) return
    try {
      await deleteUser(u.username)
      await fetchUsers()
    } catch (err: any) { alert(err.message) }
  }

  return (
    <div className="flex flex-col gap-6 max-w-3xl mx-auto">
      {/* ── Create user form ───────────────────────── */}
      <section className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">
          Register New User
        </h2>
        <form onSubmit={handleCreate} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Username *</label>
            <input
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              pattern="^[a-zA-Z0-9_\-]+$"
              minLength={3}
              maxLength={64}
              placeholder="john_doe"
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-100
                         focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Password *</label>
            <input
              required
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={6}
              placeholder="Min 6 characters"
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-100
                         focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Full Name</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Optional"
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-100
                         focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as 'user' | 'admin')}
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-100
                         focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          {formError && (
            <div className="sm:col-span-2 text-sm text-red-400 bg-red-950/40 border border-red-800/50 rounded-lg px-3 py-2">
              {formError}
            </div>
          )}
          {formSuccess && (
            <div className="sm:col-span-2 text-sm text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 rounded-lg px-3 py-2">
              {formSuccess}
            </div>
          )}

          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={submitting}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium
                         rounded-lg px-6 py-2 text-sm transition-colors"
            >
              {submitting ? 'Creating…' : 'Create User'}
            </button>
          </div>
        </form>
      </section>

      {/* ── Users list ─────────────────────────────── */}
      <section className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">
          All Users
        </h2>

        {loadingUsers ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : fetchError ? (
          <p className="text-sm text-red-400">{fetchError}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs font-mono text-slate-500 uppercase tracking-wider border-b border-border">
                  <th className="text-left pb-2 pr-4">Username</th>
                  <th className="text-left pb-2 pr-4">Full Name</th>
                  <th className="text-left pb-2 pr-4">Role</th>
                  <th className="text-left pb-2 pr-4">Status</th>
                  <th className="text-left pb-2 pr-4">Created By</th>
                  <th className="text-left pb-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users.map((u) => (
                  <tr key={u.username} className="text-slate-300">
                    <td className="py-2.5 pr-4 font-medium">{u.username}</td>
                    <td className="py-2.5 pr-4 text-slate-400">{u.full_name ?? '—'}</td>
                    <td className="py-2.5 pr-4">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
                        ${u.role === 'admin' ? 'bg-indigo-900/60 text-indigo-300' : 'bg-slate-800 text-slate-400'}`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className={`inline-flex items-center gap-1 text-xs
                        ${u.is_active ? 'text-emerald-400' : 'text-slate-600'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                        {u.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-slate-500 text-xs">{u.created_by ?? 'system'}</td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-3">
                        {u.is_active ? (
                          <button
                            onClick={() => handleDeactivate(u)}
                            className="text-xs text-amber-400 hover:text-amber-300 transition-colors"
                          >
                            Deactivate
                          </button>
                        ) : (
                          <>
                            <button
                              onClick={() => handleReactivate(u)}
                              className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                              Reactivate
                            </button>
                            <button
                              onClick={() => handleDelete(u)}
                              className="text-xs text-red-400 hover:text-red-300 transition-colors"
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
