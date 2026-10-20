import { useState } from 'react'
import { useAuthStore } from '../store/authStore'

export function LoginPage() {
  const login = useAuthStore((s) => s.login)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const [usernameError, setUsernameError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setUsernameError(null)
    setPasswordError(null)
    setGeneralError(null)

    if (!username.trim()) { setUsernameError('Username is required'); return }
    if (!password)         { setPasswordError('Password is required');  return }

    setSubmitting(true)
    try {
      await login(username.trim(), password)
    } catch (err: any) {
      let detail = 'Something went wrong. Please try again.'
      try {
        const raw: string = err.message ?? ''
        const jsonStart = raw.indexOf('{')
        if (jsonStart !== -1) {
          const parsed = JSON.parse(raw.substring(jsonStart))
          if (parsed?.detail) detail = parsed.detail
        }
      } catch {
        if (err.message) detail = err.message
      }
      const lower = detail.toLowerCase()
      if (lower.includes("doesn't exist") || lower.includes('no account')) {
        setUsernameError(detail)
      } else if (lower.includes("doesn't match") || lower.includes('password')) {
        setPasswordError(detail)
      } else {
        setGeneralError(detail)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-slate-100">
            Live<span className="text-indigo-400">Sense</span>
          </h1>
          <p className="text-sm text-slate-500 font-mono mt-1">
            Speaker Diarization · Sentiment Analysis
          </p>
        </div>

        <div className="bg-card border border-border rounded-2xl p-8 shadow-xl">
          <h2 className="text-lg font-semibold text-slate-100 mb-6">Sign in to your account</h2>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>

            {/* Username */}
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1.5 uppercase tracking-widest">
                Username{' '}
                <span className="normal-case font-sans tracking-normal text-slate-600">or email</span>
              </label>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => { setUsername(e.target.value); setUsernameError(null) }}
                className={`w-full bg-surface border rounded-lg px-3 py-2.5 text-sm text-slate-100
                  placeholder-slate-600 focus:outline-none focus:ring-2 focus:border-transparent transition-colors
                  ${usernameError ? 'border-red-500 focus:ring-red-500' : 'border-border focus:ring-indigo-500'}`}
                placeholder="Enter your username"
              />
              {usernameError && <FieldError message={usernameError} />}
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1.5 uppercase tracking-widest">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setPasswordError(null) }}
                  className={`w-full bg-surface border rounded-lg px-3 py-2.5 pr-10 text-sm text-slate-100
                    placeholder-slate-600 focus:outline-none focus:ring-2 focus:border-transparent transition-colors
                    ${passwordError ? 'border-red-500 focus:ring-red-500' : 'border-border focus:ring-indigo-500'}`}
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                >
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
              {passwordError && <FieldError message={passwordError} />}
            </div>

            {/* General error — account disabled, network, etc. */}
            {generalError && (
              <div className="text-sm text-amber-300 bg-amber-950/40 border border-amber-700/50 rounded-lg px-3 py-2.5 flex items-start gap-2">
                <WarnIcon className="w-4 h-4 shrink-0 mt-0.5" />
                {generalError}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="mt-1 w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed
                         text-white font-medium rounded-lg py-2.5 text-sm transition-colors"
            >
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-slate-600 mt-4">
          Contact an admin to get an account
        </p>
      </div>
    </div>
  )
}

// ── Small helpers ─────────────────────────────────────────────────────── //

function FieldError({ message }: { message: string }) {
  return (
    <p className="mt-1.5 text-xs text-red-400 flex items-center gap-1">
      <WarnIcon className="w-3.5 h-3.5 shrink-0" />
      {message}
    </p>
  )
}

function WarnIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
    </svg>
  )
}

function EyeIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
    </svg>
  )
}
