import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { useLiveStore } from '../store/liveStore'

const TICK_FORMATTER = (ts: number) =>
  new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export function SentimentChart() {
  const speakers = useLiveStore((s) => s.speakers)
  const speakerColour = useLiveStore((s) => s.speakerColour)

  if (speakers.size === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
        Sentiment chart will appear here
      </div>
    )
  }

  // Merge all history points into a unified time axis keyed by timestamp
  const allTimestamps = Array.from(
    new Set(
      Array.from(speakers.values()).flatMap((s) =>
        s.sentimentHistory.map((p) => p.timestamp),
      ),
    ),
  ).sort((a, b) => a - b)

  const chartData = allTimestamps.map((ts) => {
    const point: Record<string, number | string> = { timestamp: ts }
    for (const [id, speaker] of speakers) {
      const match = speaker.sentimentHistory.find((p) => p.timestamp === ts)
      if (match) point[id] = match.score
    }
    return point
  })

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={TICK_FORMATTER}
          tick={{ fill: '#64748b', fontSize: 10 }}
          minTickGap={60}
        />
        <YAxis
          domain={[0, 1]}
          ticks={[0, 0.25, 0.5, 0.75, 1]}
          tick={{ fill: '#64748b', fontSize: 10 }}
          width={28}
        />
        <Tooltip
          contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d3a', borderRadius: 6 }}
          labelFormatter={(v: number) => TICK_FORMATTER(v)}
          formatter={(value: number, name: string) => [`${(value * 100).toFixed(0)}%`, name]}
        />
        <ReferenceLine y={0.65} stroke="#10b981" strokeDasharray="4 4" opacity={0.4} />
        <ReferenceLine y={0.40} stroke="#f43f5e" strokeDasharray="4 4" opacity={0.4} />
        {Array.from(speakers.keys()).map((id) => (
          <Line
            key={id}
            type="monotone"
            dataKey={id}
            stroke={speakerColour(id)}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
