import { useRef, useEffect } from 'react'
import { useLiveStore, type AppTheme } from '../store/liveStore'

interface SettingsPanelProps {
  open: boolean
  onClose: () => void
}

const SOURCE_LANGS = [
  { code: 'en', label: 'English' },
  // { code: 'fr', label: 'French' },
  // { code: 'de', label: 'German' },
  // { code: 'es', label: 'Spanish' },
  // { code: 'it', label: 'Italian' },
  // { code: 'pt', label: 'Portuguese' },
  // { code: 'nl', label: 'Dutch' },
  // { code: 'ru', label: 'Russian' },
  // { code: 'zh', label: 'Chinese' },
  // { code: 'ja', label: 'Japanese' },
  // { code: 'ko', label: 'Korean' },
  // { code: 'ar', label: 'Arabic' },
  // { code: 'hi', label: 'Hindi' },
  { code: 'ta', label: 'Tamil' },
  // { code: 'tr', label: 'Turkish' },
  // { code: 'pl', label: 'Polish' },
  // { code: 'auto', label: 'Auto-detect' },
]

const THEMES: { id: AppTheme; label: string; surface: string; card: string; accent: string }[] = [
  { id: 'dark',     label: 'Dark',     surface: '#0f1117', card: '#1a1d27', accent: '#6366f1' },
  { id: 'midnight', label: 'Midnight', surface: '#06090f', card: '#0c1520', accent: '#22d3ee' },
  { id: 'ember',    label: 'Ember',    surface: '#110e0a', card: '#1c1812', accent: '#f59e0b' },
  { id: 'forest',   label: 'Forest',   surface: '#080f0b', card: '#101c14', accent: '#10b981' },
  { id: 'light',    label: 'Light',    surface: '#f1f5f9', card: '#ffffff',  accent: '#6366f1' },
]


const DEEPGRAM_MODELS = [
  { value: 'nova-3', label: 'Nova 3', desc: 'Best accuracy · latest' },
  { value: 'nova-2', label: 'Nova 2', desc: 'High accuracy' },
  { value: 'nova', label: 'Nova', desc: 'Fast + accurate' },
  { value: 'enhanced', label: 'Enhanced', desc: 'Balanced' },
  { value: 'base', label: 'Base', desc: 'Fastest' },
]

const ENDPOINTING_OPTIONS = [
  { value: 0, label: 'Off', desc: 'Deepgram decides' },
  { value: 300, label: '300 ms', desc: 'Recommended' },
  { value: 500, label: '500 ms', desc: 'More context' },
  { value: 1000, label: '1 s', desc: 'Slow but complete' },
]

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const pipelineRunning = useLiveStore((s) => s.pipelineRunning)
  const settings = useLiveStore((s) => s.dgSettings)
  const updateSettings = useLiveStore((s) => s.updateDgSettings)
  const theme = useLiveStore((s) => s.theme)
  const setTheme = useLiveStore((s) => s.setTheme)

  const panelRef = useRef<HTMLDivElement>(null)
  const locked = pipelineRunning

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Panel */}
      <div
        ref={panelRef}
        className={`
          fixed top-0 right-0 h-full w-80 bg-card border-l border-border
          shadow-2xl z-50 flex flex-col
          transform transition-transform duration-300 ease-in-out
          ${open ? 'translate-x-0' : 'translate-x-full'}
        `}
        aria-label="Settings panel"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Settings</h2>
            <p className="text-xs text-slate-500 font-mono mt-0.5">Deepgram Live Transcription</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 transition-colors text-lg leading-none p-1"
            aria-label="Close settings"
          >
            ✕
          </button>
        </div>

        {locked && (
          <div className="mx-4 mt-3 px-3 py-2 rounded-lg bg-amber-950/60 border border-amber-700/50 text-xs font-mono text-amber-400">
            Settings are locked while a session is running.
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">

          {/* Theme */}
          <div>
            <p className="text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
              Theme
            </p>
            <div className="grid grid-cols-5 gap-2">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTheme(t.id)}
                  title={t.label}
                  className={`relative flex flex-col items-center gap-1.5 p-2 rounded-lg border transition-all
                    ${theme === t.id
                      ? 'border-indigo-500 ring-1 ring-indigo-500/50'
                      : 'border-slate-700 hover:border-slate-500'}
                  `}
                >
                  {/* Mini preview swatch */}
                  <div
                    className="w-full h-7 rounded-md overflow-hidden flex"
                    style={{ background: t.surface }}
                  >
                    <div className="flex-1 m-1 rounded" style={{ background: t.card }} />
                    <div className="w-1.5 self-stretch my-1 mr-1 rounded-full" style={{ background: t.accent }} />
                  </div>
                  <span className="text-[10px] font-mono text-slate-400 leading-none">{t.label}</span>
                  {theme === t.id && (
                    <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-indigo-400" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Transcription engine */}
          <fieldset disabled={locked}>
            <legend className="text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
              Transcription Engine
            </legend>
            <div className="space-y-1.5">
              <label className={`flex items-center justify-between px-3 py-2.5 rounded-lg border cursor-pointer transition-colors
                ${settings.useDeepgram
                  ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
                  : 'border-slate-700 hover:border-slate-600 text-slate-300'}
                ${locked ? 'opacity-40 cursor-not-allowed' : ''}
              `}>
                <div>
                  <span className="text-sm font-semibold">Deepgram</span>
                  <p className="text-xs text-slate-500">~300ms · neural diarization</p>
                </div>
                <input type="radio" name="engine" checked={settings.useDeepgram}
                  onChange={() => updateSettings({ useDeepgram: true })}
                  className="accent-indigo-500" disabled={locked} />
              </label>
              <label className={`flex items-center justify-between px-3 py-2.5 rounded-lg border cursor-pointer transition-colors
                ${!settings.useDeepgram
                  ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
                  : 'border-slate-700 hover:border-slate-600 text-slate-300'}
                ${locked ? 'opacity-40 cursor-not-allowed' : ''}
              `}>
                <div>
                  <span className="text-sm font-semibold">Whisper (Local)</span>
                  <p className="text-xs text-slate-500">~1-2s · runs on-Local Device</p>
                </div>
                <input type="radio" name="engine" checked={!settings.useDeepgram}
                  onChange={() => updateSettings({ useDeepgram: false })}
                  className="accent-indigo-500" disabled={locked} />
              </label>
            </div>
          </fieldset>

          {/* Deepgram-only settings */}
          <div className={`space-y-6 transition-opacity ${settings.useDeepgram ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>

          {/* Language */}
          <fieldset disabled={locked}>
            <legend className="text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
              Language
            </legend>
            <select
              value={settings.sourceLang}
              onChange={(e) => updateSettings({ sourceLang: e.target.value })}
              className="w-full text-sm font-mono bg-slate-800 border border-slate-700 text-slate-200
                         rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500
                         disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {SOURCE_LANGS.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </fieldset>

          {/* Model */}
          <fieldset disabled={locked}>
            <legend className="text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
              Model
            </legend>
            <div className="space-y-1.5">
              {DEEPGRAM_MODELS.map((m) => (
                <label
                  key={m.value}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-lg border cursor-pointer transition-colors
                    ${settings.deepgramModel === m.value
                      ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
                      : 'border-slate-700 hover:border-slate-600 text-slate-300'}
                    ${locked ? 'opacity-40 cursor-not-allowed' : ''}
                  `}
                >
                  <div>
                    <span className="text-sm font-semibold">{m.label}</span>
                    <span className="ml-2 text-xs text-slate-500">{m.desc}</span>
                  </div>
                  <input
                    type="radio"
                    name="deepgramModel"
                    value={m.value}
                    checked={settings.deepgramModel === m.value}
                    onChange={() => updateSettings({ deepgramModel: m.value })}
                    className="accent-indigo-500"
                    disabled={locked}
                  />
                </label>
              ))}
            </div>
          </fieldset>

          {/* Diarization */}
          <fieldset disabled={locked}>
            <legend className="text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
              Speaker Diarization
            </legend>
            <label className={`flex items-center justify-between px-3 py-3 rounded-lg border
              ${settings.diarize ? 'border-indigo-500 bg-indigo-600/10' : 'border-slate-700'}
              ${locked ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
            `}>
              <div>
                <span className="text-sm text-slate-200">Identify speakers</span>
                <p className="text-xs text-slate-500 mt-0.5">Labels each word with a speaker ID</p>
              </div>
              <div className="relative">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={settings.diarize}
                  onChange={(e) => updateSettings({ diarize: e.target.checked })}
                  disabled={locked}
                />
                <div className={`w-10 h-5 rounded-full transition-colors
                  ${settings.diarize ? 'bg-indigo-600' : 'bg-slate-700'}`}
                />
                <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform
                  ${settings.diarize ? 'translate-x-5' : 'translate-x-0'}`}
                />
              </div>
            </label>
          </fieldset>

          {/* Endpointing */}
          <fieldset disabled={locked}>
            <legend className="text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
              Endpointing
            </legend>
            <p className="text-xs text-slate-500 mb-2">
              Silence duration before Deepgram finalises a segment
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {ENDPOINTING_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex flex-col px-3 py-2 rounded-lg border cursor-pointer transition-colors text-center
                    ${settings.endpointing === opt.value
                      ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
                      : 'border-slate-700 hover:border-slate-600 text-slate-300'}
                    ${locked ? 'opacity-40 cursor-not-allowed' : ''}
                  `}
                >
                  <span className="text-sm font-semibold">{opt.label}</span>
                  <span className="text-xs text-slate-500">{opt.desc}</span>
                  <input
                    type="radio"
                    name="endpointing"
                    value={opt.value}
                    checked={settings.endpointing === opt.value}
                    onChange={() => updateSettings({ endpointing: opt.value })}
                    className="sr-only"
                    disabled={locked}
                  />
                </label>
              ))}
            </div>
          </fieldset>

          {/* Punctuation */}
          <fieldset disabled={locked}>
            <legend className="text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
              Punctuation
            </legend>
            <label className={`flex items-center justify-between px-3 py-3 rounded-lg border
              ${settings.punctuate ? 'border-indigo-500 bg-indigo-600/10' : 'border-slate-700'}
              ${locked ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
            `}>
              <div>
                <span className="text-sm text-slate-200">Add punctuation</span>
                <p className="text-xs text-slate-500 mt-0.5">Commas, periods, question marks</p>
              </div>
              <div className="relative">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={settings.punctuate}
                  onChange={(e) => updateSettings({ punctuate: e.target.checked })}
                  disabled={locked}
                />
                <div className={`w-10 h-5 rounded-full transition-colors
                  ${settings.punctuate ? 'bg-indigo-600' : 'bg-slate-700'}`}
                />
                <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform
                  ${settings.punctuate ? 'translate-x-5' : 'translate-x-0'}`}
                />
              </div>
            </label>
          </fieldset>

          </div>{/* end Deepgram-only */}

        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-border">
          <p className="text-xs text-slate-600 font-mono text-center">
            Settings apply to the next session
          </p>
        </div>
      </div>
    </>
  )
}
