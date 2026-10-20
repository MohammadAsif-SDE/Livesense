import { useEffect, useRef, useState } from 'react'
import { useLiveStore } from '../store/liveStore'
import { cn, polarityBg, polarityColour } from '../lib/utils'

export function TranscriptPanel() {
  const transcript = useLiveStore((s) => s.transcript)
  const pipelineRunning = useLiveStore((s) => s.pipelineRunning)
  const speakerColour = useLiveStore((s) => s.speakerColour)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Word-by-word typewriter animation state
  const [animatingId, setAnimatingId] = useState<string | null>(null)
  const [revealedWords, setRevealedWords] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Auto-scroll to newest entry
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript.length])

  // Start typewriter on every new entry
  useEffect(() => {
    if (transcript.length === 0) return
    const newest = transcript[transcript.length - 1]
    const raw = newest.text
    const words = raw.split(/\s+/).filter(Boolean)

    // Clear any in-progress animation
    if (timerRef.current) clearInterval(timerRef.current)

    setAnimatingId(newest.id)
    setRevealedWords(1)

    let count = 1
    timerRef.current = setInterval(() => {
      count++
      setRevealedWords(count)
      if (count >= words.length) {
        clearInterval(timerRef.current!)
        timerRef.current = null
        setAnimatingId(null) // animation done
      }
    }, 110) // ~110 ms per word — feels natural, not too fast/slow

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transcript.length])

  return (
    <div className="flex flex-col h-full">
      {/* Entries */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {transcript.length === 0 && !pipelineRunning && (
          <div className="text-slate-500 text-sm text-center mt-8">
            Transcript will appear here when the pipeline is running
          </div>
        )}
        {transcript.length === 0 && pipelineRunning && (
          <div className="flex flex-col items-center gap-3 mt-12 text-slate-400">
            <svg
              className="animate-spin h-7 w-7 text-indigo-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12" cy="12" r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v4l3-3-3-3v4a10 10 0 100 20v-4l-3 3 3 3v-4a8 8 0 01-8-8z"
              />
            </svg>
            <p className="text-xs font-mono text-slate-500 animate-pulse">
              Listening… first words will appear in ~3s
            </p>
          </div>
        )}
        {transcript.map((entry) => {
          const colour = speakerColour(entry.speaker_id)
          const fullText = entry.text

          // For the animating entry, reveal word by word; everything else shows in full.
          const isAnimating = entry.id === animatingId
          const displayText = isAnimating
            ? fullText.split(/\s+/).slice(0, revealedWords).join(' ')
            : fullText
          const isCursorVisible = isAnimating && timerRef.current !== null

          return (
            <div
              key={entry.id}
              className={cn(
                'rounded-lg border px-3 py-2 text-sm transition-all',
                polarityBg(entry.polarity),
              )}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs font-semibold" style={{ color: colour }}>
                  {entry.speaker_id}
                </span>
                <span className={cn('text-xs font-mono', polarityColour(entry.polarity))}>
                  {entry.polarity}
                </span>
                <span className="ml-auto text-xs text-slate-600 font-mono">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
                {entry.language !== 'en' && (
                  <span className="text-xs text-slate-500 uppercase font-mono">
                    [{entry.language}]
                  </span>
                )}
              </div>
              <p className="text-slate-200 leading-relaxed">
                {displayText}
                {isCursorVisible && (
                  <span className="inline-block w-0.5 h-4 bg-indigo-400 ml-0.5 align-middle animate-pulse" />
                )}
              </p>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
