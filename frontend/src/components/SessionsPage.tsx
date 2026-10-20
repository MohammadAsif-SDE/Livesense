/**
 * components/SessionsPage.tsx
 * Browse all sessions (live + uploads), drill into events and speaker stats.
 */

import { useCallback, useEffect, useState } from 'react'
import { deleteSession, getSession, getSessionEvents, getSessionSpeakers, listSessions, listUsers } from '../lib/api'
import type { Session, SessionEvent, SpeakerStats, UserRecord } from '../types'
import { useAuthStore } from '../store/authStore'

// ── Helpers ──────────────────────────────────────────────────────────── //

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString()
}

function fmtDuration(s: number) {
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

function fmt(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const STATUS_COLORS: Record<string, string> = {
  pending:    'text-yellow-300 bg-yellow-500/20 border-yellow-500/50',
  processing: 'text-blue-300 bg-blue-500/20 border-blue-500/50',
  completed:  'text-green-400 bg-emerald-500/20 border-emerald-500/50',
  failed:     'text-red-300 bg-red-500/20 border-red-500/50',
}

const POLARITY_COLORS: Record<string, string> = {
  positive: 'text-emerald-400',
  negative: 'text-red-400',
  neutral:  'text-slate-400',
}

// ── Session list ─────────────────────────────────────────────────────── //

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded border ${STATUS_COLORS[status] ?? 'text-slate-400'}`}>
      {status}
    </span>
  )
}

// ── Speaker bar ──────────────────────────────────────────────────────── //

function SpeakerCard({ s }: { s: SpeakerStats }) {
  const dominant = s.dominant_emotion ?? '—'
  const polarities = s.polarity_counts ?? {}
  const total = Object.values(polarities).reduce((a, b) => a + b, 0) || 1

  return (
    <div className="bg-slate-800/60 rounded-lg p-4 border border-border">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-sm text-indigo-300">{s.speaker_id}</span>
        <span className="text-xs text-slate-400">{s.total_utterances} utterances · {s.total_words} words</span>
      </div>
      <div className="flex gap-4 text-xs text-slate-400 mb-3">
        <span>Emotion: <span className="text-slate-200">{dominant}</span></span>
        <span>Avg score: <span className="text-slate-200">{(s.avg_sentiment_score * 100).toFixed(0)}%</span></span>
        <span>Speaking: <span className="text-slate-200">{fmtDuration(s.total_speaking_seconds)}</span></span>
      </div>
      {/* Polarity bar */}
      <div className="flex rounded overflow-hidden h-2">
        {(['positive', 'negative', 'neutral'] as const).map(p => {
          const pct = ((polarities[p] ?? 0) / total) * 100
          const bg = p === 'positive' ? 'bg-emerald-500' : p === 'negative' ? 'bg-red-500' : 'bg-slate-500'
          return pct > 0 ? <div key={p} className={bg} style={{ width: `${pct}%` }} /> : null
        })}
      </div>
    </div>
  )
}

// ── Sentiment Ring ────────────────────────────────────────────────────── //

function SessionSummaryPanel({ session }: { session: Session }) {
  const { summary } = session
  if (!summary) return null

  const pos   = summary.polarity_distribution.positive ?? 0
  const neg   = summary.polarity_distribution.negative ?? 0
  const neu   = summary.polarity_distribution.neutral  ?? 0
  const total = pos + neg + neu || 1

  const rings = [
    { key: 'positive', label: 'Positive', value: pos, stroke: '#10b981', track: '#052e16', bg: 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800/40' },
    { key: 'negative', label: 'Negative', value: neg, stroke: '#f43f5e', track: '#4c0519', bg: 'bg-rose-50 border-rose-200 dark:bg-rose-950/30 dark:border-rose-800/40'             },
    { key: 'neutral',  label: 'Neutral',  value: neu, stroke: '#eab308', track: '#422006', bg: 'bg-yellow-50 border-yellow-200 dark:bg-yellow-950/30 dark:border-yellow-700/40'      },
  ]

  const R = 26; const sz = 68; const cx = sz / 2; const cy = sz / 2
  const sw = 8;  const circ = 2 * Math.PI * R

  const stats = [
    { label: 'Events',   value: String(summary.event_count) },
    { label: 'Speakers', value: String(summary.speaker_count) },
    { label: 'Duration', value: fmtDuration(summary.total_duration_seconds) },
    { label: 'Emotion',  value: summary.dominant_emotion ?? '—' },
  ]

  return (
    <div className="bg-card border border-border p-5 flex flex-col gap-5">
      {/* ── Stats capsule ── */}
      <div className="flex items-stretch border border-border divide-x divide-border overflow-hidden">
        {stats.map(({ label, value }) => (
          <div key={label} className="flex-1 flex flex-col items-center justify-center px-4 py-2.5">
            <div className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">{label}</div>
            <div className="text-sm font-bold text-slate-100 mt-0.5">{value}</div>
          </div>
        ))}
      </div>

      {/* ── Sentiment rings ── */}
      <div>
        <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-3">Sentiment Breakdown</p>
        <div className="flex gap-3">
          {rings.map(({ key, label, value, stroke, track, bg }) => {
            const pct  = value / total
            const dash = pct * circ
            const gap  = circ - dash
            return (
              <div key={key} className={`flex items-center gap-3 border px-3 py-2.5 flex-1 ${bg}`}>
                <svg width={sz} height={sz} viewBox={`0 0 ${sz} ${sz}`} className="shrink-0">
                  <circle cx={cx} cy={cy} r={R} fill="none" stroke={track} strokeWidth={sw} />
                  <circle
                    cx={cx} cy={cy} r={R} fill="none"
                    stroke={stroke} strokeWidth={sw}
                    strokeDasharray={`${dash} ${gap}`} strokeLinecap="butt"
                    style={{ transform: 'rotate(-90deg)', transformOrigin: `${cx}px ${cy}px` }}
                  />
                  <text x={cx} y={cy + 5} textAnchor="middle" className="fill-slate-100" fontSize="14" fontWeight="700">{value}</text>
                </svg>
                <div className="min-w-0">
                  <div className="text-xs font-semibold" style={{ color: stroke }}>{label}</div>
                  <div className="text-lg font-bold text-slate-100 leading-none mt-0.5" style={{ color: stroke }}>{(pct * 100).toFixed(0)}%</div>
                  <div className="text-[10px] text-slate-300 mt-0.5">{value} events</div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Audio Player ──────────────────────────────────────────────────────── //

function AudioPlayer({ sessionId, sessionType }: { sessionId: string; sessionType: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filename, setFilename] = useState<string>('')

  useEffect(() => {
    let url: string | null = null
    setLoading(true)
    setError(null)

    import('../lib/api').then(({ getToken }) => {
      const token = getToken()
      fetch(`/api/sessions/${sessionId}/audio`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then(async (res) => {
          if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
          const cd = res.headers.get('content-disposition') ?? ''
          const match = cd.match(/filename="?([^"]+)"?/)
          if (match) setFilename(match[1])
          return res.blob()
        })
        .then((blob) => {
          url = URL.createObjectURL(blob)
          setBlobUrl(url)
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    })

    return () => { if (url) URL.revokeObjectURL(url) }
  }, [sessionId])

  const handleDownload = () => {
    if (!blobUrl) return
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = filename || `session_${sessionId}.wav`
    a.click()
  }

  return (
    <div className="bg-card border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-mono text-slate-500 uppercase tracking-widest">
          {sessionType === 'live' ? '🎙 Recorded Audio' : '📁 Uploaded Audio'}
        </h3>
        {blobUrl && (
          <button
            onClick={handleDownload}
            className="text-xs text-indigo-400 hover:text-indigo-300 border border-indigo-800/50 px-3 py-1 transition-colors flex items-center gap-1.5"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Download
          </button>
        )}
      </div>

      {loading && <p className="text-xs text-slate-500">Loading audio…</p>}
      {error   && <p className="text-xs text-red-400">Failed to load audio: {error}</p>}
      {blobUrl && (
        <audio controls className="w-full" src={blobUrl}>
          Your browser does not support the audio element.
        </audio>
      )}
    </div>
  )
}

function SessionDetail({ sessionId, onBack }: { sessionId: string; onBack: () => void }) {
  const [session, setSession] = useState<Session | null>(null)
  const [events, setEvents] = useState<SessionEvent[]>([])
  const [totalEvents, setTotalEvents] = useState(0)
  const [speakers, setSpeakers] = useState<SpeakerStats[]>([])
  const [tab, setTab] = useState<'transcript' | 'speakers'>('transcript')
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const PAGE = 100

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, ev, sp] = await Promise.all([
        getSession(sessionId),
        getSessionEvents(sessionId, { limit: PAGE, skip: page * PAGE }),
        getSessionSpeakers(sessionId).catch(() => []),
      ])
      setSession(s)
      setEvents(ev.events ?? [])
      setTotalEvents(ev.total ?? 0)
      setSpeakers(sp)
    } finally {
      setLoading(false)
    }
  }, [sessionId, page])

  useEffect(() => { load() }, [load])

  // Auto-refresh while processing
  useEffect(() => {
    if (session?.status === 'processing' || session?.status === 'pending') {
      const t = setTimeout(load, 3000)
      return () => clearTimeout(t)
    }
  }, [session?.status, load])

  if (loading && !session) {
    return <div className="text-slate-400 text-sm">Loading…</div>
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Back + title */}
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="text-slate-400 hover:text-slate-200 text-sm">← Back</button>
        <span className="text-slate-500">/</span>
        <span className="font-mono text-xs text-slate-400 truncate">{sessionId}</span>
        {session && <StatusBadge status={session.status} />}
      </div>

      {/* Summary */}
      {session?.summary && <SessionSummaryPanel session={session} />}

      {/* Audio player */}
      {session && (session as any).audio_path && (
        <AudioPlayer sessionId={session.session_id} sessionType={session.type} />
      )}

      {/* Processing status */}
      {(session?.status === 'processing' || session?.status === 'pending') && (
        <div className="bg-blue-950/30 border border-blue-700 rounded-lg px-4 py-3 text-sm text-blue-300 flex items-center gap-2">
          <span className="animate-spin inline-block">⟳</span> Processing… results appear below as they arrive.
        </div>
      )}
      {session?.status === 'failed' && (
        <div className="bg-red-950/30 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          Failed: {session.error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-border pb-2">
        {(['transcript', 'speakers'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-sm px-3 py-1 rounded-md transition-colors ${tab === t ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
          >
            {t === 'transcript' ? `Transcript (${totalEvents})` : `Speakers (${speakers.length})`}
          </button>
        ))}
      </div>

      {/* Transcript tab */}
      {tab === 'transcript' && (
        <div className="flex flex-col gap-2 pr-1">
          {events.length === 0 && (
            <div className="text-slate-500 text-sm py-8 text-center">No transcript yet</div>
          )}
          {events.map(ev => (
            <div key={ev.event_index} className="bg-slate-800/50 border border-border/50 px-4 py-3 flex flex-col gap-2">
              {/* Header row: speaker · timestamp on left, meta on right */}
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-indigo-400">{ev.speaker_id}</span>
                  <span className="text-slate-600 text-xs">·</span>
                  <span className="font-mono text-xs text-slate-400">{fmtDuration(ev.offset_seconds)}</span>
                </div>
                <div className="flex items-center gap-3 text-xs shrink-0">
                  <span className={`font-semibold ${POLARITY_COLORS[ev.polarity]}`}>{ev.polarity}</span>
                  {ev.dominant_emotion && (
                    <span className="text-slate-400 bg-slate-700/50 px-1.5 py-0.5 rounded font-mono">{ev.dominant_emotion}</span>
                  )}
                  <span className="text-slate-400 tabular-nums">{(ev.final_score * 100).toFixed(0)}% score</span>
                  {ev.language && ev.language !== 'en' && (
                    <span className="text-slate-500 font-mono">[{ev.language}]</span>
                  )}
                </div>
              </div>
              {/* Transcript text */}
              <p className="text-sm text-slate-200 leading-relaxed">{ev.transcript}</p>
            </div>
          ))}
          {/* Pagination */}
          {totalEvents > PAGE && (
            <div className="flex justify-center gap-3 mt-2">
              <button
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
                className="text-xs px-3 py-1 rounded border border-border text-slate-400 disabled:opacity-30"
              >← Prev</button>
              <span className="text-xs text-slate-500 self-center">
                {page * PAGE + 1}–{Math.min((page + 1) * PAGE, totalEvents)} of {totalEvents}
              </span>
              <button
                disabled={(page + 1) * PAGE >= totalEvents}
                onClick={() => setPage(p => p + 1)}
                className="text-xs px-3 py-1 rounded border border-border text-slate-400 disabled:opacity-30"
              >Next →</button>
            </div>
          )}
        </div>
      )}

      {/* Speakers tab */}
      {tab === 'speakers' && (
        <div className="flex flex-col gap-3">
          {speakers.length === 0 && (
            <div className="text-slate-500 text-sm py-8 text-center">No speaker data yet</div>
          )}
          {speakers.map(s => <SpeakerCard key={s.speaker_id} s={s} />)}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────── //

export function SessionsPage() {
  const currentUser = useAuthStore((s) => s.user)
  const isAdmin = currentUser?.role === 'admin'

  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')          // admin only
  const [allUsers, setAllUsers] = useState<UserRecord[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // Fetch user list for admin filter dropdown
  useEffect(() => {
    if (isAdmin) {
      listUsers().then(setAllUsers).catch(() => {})
    }
  }, [isAdmin])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listSessions({
        type: typeFilter || undefined,
        status: statusFilter || undefined,
        user: isAdmin ? (userFilter || undefined) : undefined,
        limit: 100,
      })
      setSessions(data)
    } finally {
      setLoading(false)
    }
  }, [typeFilter, statusFilter, userFilter, isAdmin])

  useEffect(() => { load() }, [load])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm('Delete this session and all its data?')) return
    setDeletingId(id)
    await deleteSession(id)
    setDeletingId(null)
    load()
  }

  if (selectedId) {
    return <SessionDetail sessionId={selectedId} onBack={() => { setSelectedId(null); load() }} />
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Sessions</h2>
        <button onClick={load} className="text-xs text-slate-400 hover:text-slate-200 border border-border rounded px-2 py-1">
          ↺ Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="bg-slate-800 border border-border rounded px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">All types</option>
          <option value="live">Live</option>
          <option value="upload">Upload</option>
        </select>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="bg-slate-800 border border-border rounded px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="processing">Processing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
        {isAdmin && (
          <select
            value={userFilter}
            onChange={e => setUserFilter(e.target.value)}
            className="bg-slate-800 border border-border rounded px-3 py-1.5 text-sm text-slate-300"
          >
            <option value="">All users</option>
            {allUsers.map(u => (
              <option key={u.username} value={u.username}>{u.username}</option>
            ))}
          </select>
        )}
      </div>

      {/* List */}
      {loading && sessions.length === 0 && (
        <div className="text-slate-500 text-sm py-12 text-center">Loading…</div>
      )}
      {!loading && sessions.length === 0 && (
        <div className="text-slate-500 text-sm py-12 text-center">
          No sessions yet. Run a live session or upload a file.
        </div>
      )}

      <div className="flex flex-col gap-2">
        {sessions.map(s => (
          <div
            key={s.session_id}
            onClick={() => setSelectedId(s.session_id)}
            className="bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-4 cursor-pointer hover:border-indigo-500 transition-colors"
          >
            {/* Type icon */}
            <div className="text-2xl shrink-0">{s.type === 'live' ? '🎙' : '📁'}</div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs text-slate-400 truncate">{s.session_id}</span>
                <StatusBadge status={s.status} />
                <span className="text-xs text-slate-600 capitalize">{s.type}</span>
                {isAdmin && (s as any).created_by && (
                  <span className="text-xs text-indigo-300 bg-indigo-500/20 border border-indigo-400/40 px-1.5 py-0.5 rounded font-mono">
                    👤 {(s as any).created_by}
                  </span>
                )}
              </div>
              <div className="flex gap-4 text-xs text-slate-500">
                <span>{fmtDate(s.created_at)}</span>
                {s.file && <span>{s.file.original_name} · {fmt(s.file.size_bytes)}</span>}
                {s.summary && (
                  <>
                    <span>{s.summary.event_count} events</span>
                    <span>{s.summary.speaker_count} speakers</span>
                    <span>{fmtDuration(s.summary.total_duration_seconds)}</span>
                  </>
                )}
              </div>
            </div>

            {/* Delete */}
            <button
              onClick={e => handleDelete(e, s.session_id)}
              disabled={deletingId === s.session_id}
              className="text-slate-600 hover:text-red-400 transition-colors text-lg disabled:opacity-30 shrink-0"
              title="Delete session"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
