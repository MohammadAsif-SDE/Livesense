import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: Parameters<typeof clsx>) {
  return twMerge(clsx(...inputs))
}

export function polarityColour(polarity: string): string {
  switch (polarity) {
    case 'positive': return 'text-emerald-400'
    case 'negative': return 'text-rose-400'
    default:         return 'text-slate-400'
  }
}

export function polarityBg(polarity: string): string {
  switch (polarity) {
    case 'positive': return 'bg-emerald-500/20 border-emerald-500/40'
    case 'negative': return 'bg-rose-500/20 border-rose-500/40'
    default:         return 'bg-slate-500/20 border-slate-500/40'
  }
}

export function scoreToPercent(score: number): string {
  return `${(score * 100).toFixed(0)}%`
}
