import { useState } from 'react'
import { useLiveStore } from '../store/liveStore'
import { SettingsPanel } from './SettingsPanel'
import { cn } from '../lib/utils'

const SOURCE_LANGS = [
  { code: 'en', label: 'English' },
  { code: 'ta', label: 'Tamil' },
]

export function SettingsSummary() {
  const [open, setOpen] = useState(false)
  const dgSettings = useLiveStore((s) => s.dgSettings)
  const pipelineRunning = useLiveStore((s) => s.pipelineRunning)

  return (
    <>
      <SettingsPanel open={open} onClose={() => setOpen(false)} />

      <div className="flex items-center justify-between border border-border bg-card px-4 py-2">
        {/* Settings summary text */}
        <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
          <span className={dgSettings.useDeepgram ? 'text-indigo-400' : 'text-slate-400'}>
            {dgSettings.useDeepgram ? `Deepgram · ${dgSettings.deepgramModel}` : 'Local · Whisper'}
          </span>
          <span className="text-slate-700">·</span>
          <span>
            {SOURCE_LANGS.find((l) => l.code === dgSettings.sourceLang)?.label ?? dgSettings.sourceLang}
          </span>
          {dgSettings.useDeepgram && dgSettings.diarize && (
            <>
              <span className="text-slate-700">·</span>
              <span>diarize</span>
            </>
          )}
        </div>

        {/* Gear button */}
        <button
          onClick={() => setOpen(true)}
          title="Pipeline settings"
          disabled={pipelineRunning}
          className={cn(
            'p-1.5 text-slate-400 hover:text-slate-100 hover:bg-slate-700 transition-colors',
            pipelineRunning && 'text-slate-700 cursor-default pointer-events-none',
          )}
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </div>
    </>
  )
}
