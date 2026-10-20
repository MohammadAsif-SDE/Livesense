import { useState, useEffect } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useLiveStore } from './store/liveStore'
import { useAuthStore } from './store/authStore'
import { ControlBar } from './components/ControlBar'
import { SpeakerTimeline } from './components/SpeakerTimeline'
import { SentimentChart } from './components/SentimentChart'
import { TranscriptPanel } from './components/TranscriptPanel'
import { UploadPage } from './components/UploadPage'
import { SessionsPage } from './components/SessionsPage'
import { LoginPage } from './components/LoginPage'
import { RegisterUserPage } from './components/RegisterUserPage'
import { SettingsSummary } from './components/SettingsSummary'
import './index.css'

function ConnectedBadge() {
  const connected = useLiveStore((s) => s.connected)
  return (
    <div className="flex items-center gap-1.5 text-xs font-mono">
      <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
      <span className={connected ? 'text-emerald-400' : 'text-rose-400'}>
        {connected ? 'connected' : 'disconnected'}
      </span>
    </div>
  )
}

function TranscriptCount() {
  const count = useLiveStore((s) => s.transcript.length)
  return (
    <span className="text-xs font-mono text-slate-400">
      {count} utterance{count !== 1 ? 's' : ''}
    </span>
  )
}

type Tab = 'live' | 'upload' | 'sessions' | 'users'

const TAB_KEY = 'ls_active_tab'

function getSavedTab(): Tab {
  const saved = localStorage.getItem(TAB_KEY) as Tab | null
  return saved ?? 'live'
}

export default function App() {
  useWebSocket()
  const [tab, setTab] = useState<Tab>(getSavedTab)

  const handleTabChange = (t: Tab) => {
    localStorage.setItem(TAB_KEY, t)
    setTab(t)
  }
  const theme = useLiveStore((s) => s.theme)
  const { user, loading: authLoading, restoreSession, logout } = useAuthStore()

  // Restore JWT session on mount
  useEffect(() => { restoreSession() }, [])

  useEffect(() => {
    const html = document.documentElement
    if (theme === 'dark') {
      html.removeAttribute('data-theme')
    } else {
      html.setAttribute('data-theme', theme)
    }
  }, [theme])

  // ── Auth gate ──────────────────────────────────────────
  if (authLoading && !user) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <p className="text-slate-500 font-mono text-sm">Loading…</p>
      </div>
    )
  }

  if (!user) {
    return <LoginPage />
  }

  const isAdmin = user.role === 'admin'

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'live',     label: 'Live',     icon: '🎙' },
    { id: 'upload',   label: 'Upload',   icon: '📁' },
    { id: 'sessions', label: 'Sessions', icon: '📊' },
    ...(isAdmin ? [{ id: 'users' as Tab, label: 'Users', icon: '👥' }] : []),
  ]

  return (
    <div className="h-screen overflow-hidden bg-surface text-slate-100 p-4 flex flex-col gap-4">
      {/* ── Header ──────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-border pb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">
            Live<span className="text-indigo-400">Sense</span>
          </h1>
          <p className="text-xs text-slate-500 font-mono mt-0.5">
            Real-time Speaker Diarization · Sentiment Analysis
          </p>
        </div>

        {/* Connection status + User badge + logout */}
        <div className="flex items-center gap-4 pl-3">
          {/* Connected indicator */}
          <ConnectedBadge />

          <div className="w-px h-5 bg-border" />

          <p className="text-sm text-slate-100 leading-none">
            <span className="text-slate-500 font-normal">Welcome, </span>
            <span className="font-semibold">{user.full_name ?? user.username}</span>
          </p>
          <button
            onClick={() => { if (confirm('Are you sure you want to logout?')) logout() }}
            title="Logout"
            className="w-9 h-9 flex items-center justify-center rounded-full bg-red-600 border border-red-500 text-white hover:bg-red-950/50 hover:border-red-700 hover:text-red-400 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18.36 6.64A9 9 0 1 1 5.64 6.64" />
              <line x1="12" y1="2" x2="12" y2="12" />
            </svg>
          </button>
        </div>
      </header>

      {/* ── Tab bar + ControlBar ─────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-border pb-3">
        <nav className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => handleTabChange(t.id)}
              className={`flex items-center gap-1.5 text-sm px-4 py-1.5 rounded-lg transition-colors ${
                tab === t.id
                  ? 'bg-indigo-600 text-white font-medium'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <span>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>
        {tab === 'live' && <ControlBar />}
      </div>

      {/* ── Live tab ────────────────────────────────────────── */}
      {tab === 'live' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
          {/* Left column */}
          <div className="lg:col-span-1 flex flex-col gap-4 min-h-0 h-full">
            {/* Settings summary */}
            <SettingsSummary />

            {/* Sentiment Over Time — top */}
            <section className="bg-card border border-border p-4 shrink-0">
              <h2 className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-3">
                Sentiment Over Time
              </h2>
              <SentimentChart />
            </section>

            {/* Speaker Sentiment — fills remaining height */}
            <section className="bg-card border border-border p-4 flex flex-col flex-1 min-h-0">
              <h2 className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-3">
                Speaker Sentiment
              </h2>
              <div className="flex-1 overflow-y-auto min-h-0">
                <SpeakerTimeline />
              </div>
            </section>
          </div>

          {/* Right column — transcript, same height as left */}
          <section className="lg:col-span-2 bg-card border border-border p-4 flex flex-col min-h-0 h-full">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-mono text-slate-500 uppercase tracking-widest">Live Transcript</h2>
              <TranscriptCount />
            </div>
            <div className="flex-1 overflow-hidden min-h-0">
              <TranscriptPanel />
            </div>
          </section>
        </div>
      )}

      {/* ── Upload tab ──────────────────────────────────────── */}
      {tab === 'upload' && (
        <div className="bg-card rounded-xl border border-border p-6">
          <UploadPage />
        </div>
      )}

      {/* ── Sessions tab ────────────────────────────────────── */}
      {tab === 'sessions' && (
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="bg-card border border-border p-6">
            <SessionsPage />
          </div>
        </div>
      )}

      {/* ── Users tab (admin only) ───────────────────────────── */}
      {tab === 'users' && isAdmin && (
        <div className="p-2">
          <RegisterUserPage />
        </div>
      )}
    </div>
  )
}
