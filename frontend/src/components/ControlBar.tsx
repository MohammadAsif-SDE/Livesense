import { useState, useEffect, useRef } from 'react'
import { useLiveStore } from '../store/liveStore'
import { useAudioLevel } from '../hooks/useAudioLevel'
import { cn } from '../lib/utils'
import { SettingsPanel } from './SettingsPanel'

const API_BASE = ''
const BAR_COUNT = 8

export function ControlBar() {
  const connected = useLiveStore((s) => s.connected)
  const pipelineRunning = useLiveStore((s) => s.pipelineRunning)
  const setPipelineRunning = useLiveStore((s) => s.setPipelineRunning)
  const clearAll = useLiveStore((s) => s.clearAll)
  const dgSettings = useLiveStore((s) => s.dgSettings)
  const hasData = useLiveStore((s) => s.transcript.length > 0 || s.speakers.size > 0)

  const [loading, setLoading] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [tick, setTick] = useState(0)
  const rafRef = useRef<number | null>(null)
  const audioLevel = useAudioLevel(pipelineRunning)

  // Animate bars via rAF while listening
  useEffect(() => {
    if (!pipelineRunning) return
    let last = 0
    function loop(t: number) {
      if (t - last > 50) { setTick((n) => n + 1); last = t }
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [pipelineRunning])

  async function toggle() {
    setLoading(true)
    try {
      if (pipelineRunning) {
        const res = await fetch(`${API_BASE}/stop`, { method: 'POST' })
        if (res.ok) setPipelineRunning(false)
      } else {
        clearAll()   // wipe previous session transcript before starting
        const res = await fetch(`${API_BASE}/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_lang: dgSettings.sourceLang,
            deepgram_model: dgSettings.deepgramModel,
            diarize: dgSettings.diarize,
            endpointing: dgSettings.endpointing,
            punctuate: dgSettings.punctuate,
            use_deepgram: dgSettings.useDeepgram,
          }),
        })
        if (res.ok) setPipelineRunning(true)
      }
    } catch {
      // Server unreachable — connection indicator shows this
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      <div className="flex items-center gap-3">
          {/* Listening badge + waveform */}
          {pipelineRunning && (
            <div className="flex items-center gap-2 bg-rose-950/60 border border-rose-700/50 rounded-full px-3 py-1">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500" />
              </span>
              <span className="text-xs font-mono font-semibold text-rose-300 tracking-wide">
                LISTENING
              </span>
              <div className="flex items-end gap-[2px] h-5">
                {Array.from({ length: BAR_COUNT }).map((_, i) => {
                  const phase = (i / BAR_COUNT) * Math.PI * 2
                  const wave = 0.4 + 0.6 * Math.abs(Math.sin(phase + tick * 0.18))
                  const idle = 0.15 + 0.25 * wave
                  const h = audioLevel > 0.05
                    ? Math.max(0.1, Math.min(1, audioLevel * wave * 1.8))
                    : idle
                  return (
                    <div
                      key={i}
                      className="w-[3px] rounded-full bg-rose-400 transition-all duration-75"
                      style={{ height: `${Math.round(h * 20)}px` }}
                    />
                  )
                })}
              </div>
            </div>
          )}

          {/* Start / Stop */}
          <button
            onClick={toggle}
            disabled={loading || !connected}
            className={cn(
              'px-4 py-1.5 rounded-md text-xs font-semibold font-mono transition-colors',
              pipelineRunning
                ? 'bg-rose-500 hover:bg-rose-600 text-white'
                : 'bg-indigo-600 hover:bg-indigo-700 text-white',
              (loading || !connected) && 'opacity-50 cursor-not-allowed',
            )}
          >
            {loading ? '…' : pipelineRunning ? '⏹ Stop' : '⏺ Start'}
          </button>

          {/* Clear — only when there is data to clear and pipeline is stopped */}
          {hasData && !pipelineRunning && (
            <button
              onClick={clearAll}
              className="px-3 py-1.5 rounded-md text-xs font-mono text-slate-400 hover:text-slate-100 border border-slate-700 hover:border-slate-500 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
    </>
  )
}
