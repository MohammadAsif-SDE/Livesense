import { useLiveStore } from '../store/liveStore'
import { cn, polarityBg, polarityColour } from '../lib/utils'

export function SpeakerTimeline() {
  const speakers = useLiveStore((s) => s.speakers)
  const speakerColour = useLiveStore((s) => s.speakerColour)

  if (speakers.size === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-slate-500 text-sm">
        No speakers detected yet
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {Array.from(speakers.values()).map((speaker) => {
        const colour = speakerColour(speaker.speaker_id)
        const pct = Math.round(speaker.latest_score * 100)

        return (
          <div key={speaker.speaker_id} className="flex items-center gap-3">
            {/* Speaker label */}
            <div
              className="w-28 shrink-0 text-xs font-mono font-medium truncate"
              style={{ color: colour }}
            >
              {speaker.speaker_id}
            </div>

            {/* Bar */}
            <div className="flex-1 h-5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${pct}%`,
                  backgroundColor: colour,
                  opacity: 0.85,
                }}
              />
            </div>

            {/* Score badge */}
            <div
              className={cn(
                'w-20 shrink-0 text-xs font-mono px-2 py-0.5 rounded-full border text-center',
                polarityBg(speaker.latest_polarity),
                polarityColour(speaker.latest_polarity),
              )}
            >
              {speaker.dominant_emotion ?? speaker.latest_polarity} · {pct}%
            </div>
          </div>
        )
      })}
    </div>
  )
}
