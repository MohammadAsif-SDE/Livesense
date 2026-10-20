import { create } from 'zustand'
import type {
  SpeakerEvent,
  SpeakerState,
  TranscriptEntry,
} from '../types'

// Colour palette for speakers (cycles if > 8 speakers)
const SPEAKER_COLOURS = [
  '#6366f1', '#22d3ee', '#f59e0b', '#10b981',
  '#f43f5e', '#a78bfa', '#34d399', '#fb923c',
]

// ── Deepgram settings ─────────────────────────────────────────────── //
export interface DgSettings {
  sourceLang: string
  deepgramModel: string
  diarize: boolean
  endpointing: number
  punctuate: boolean
  useDeepgram: boolean
}

const DEFAULT_DG_SETTINGS: DgSettings = {
  sourceLang: 'en',
  deepgramModel: 'nova-3',
  diarize: true,
  endpointing: 300,
  punctuate: true,
  useDeepgram: true,
}

export type AppTheme = 'dark' | 'midnight' | 'ember' | 'forest' | 'light'

interface LiveStore {
  // Connection
  connected: boolean
  pipelineRunning: boolean
  setConnected: (v: boolean) => void
  setPipelineRunning: (v: boolean) => void

  // Theme
  theme: AppTheme
  setTheme: (t: AppTheme) => void

  // Deepgram settings
  dgSettings: DgSettings
  updateDgSettings: (patch: Partial<DgSettings>) => void

  // Language settings (chosen before starting)
  sourceLang: string        // 'en', 'fr', 'auto', etc.
  setSourceLang: (v: string) => void

  // Speakers map: speaker_id → SpeakerState
  speakers: Map<string, SpeakerState>
  speakerColour: (id: string) => string
  _speakerOrder: string[]

  // Transcript
  transcript: TranscriptEntry[]

  // Ingest an event from the WebSocket
  ingestEvent: (event: SpeakerEvent) => void

  // Actions
  clearAll: () => void
}

const _savedTheme = (localStorage.getItem('ls-theme') as AppTheme) || 'dark'

export const useLiveStore = create<LiveStore>((set, get) => ({
  connected: false,
  pipelineRunning: false,
  setConnected: (v) => set({ connected: v }),
  setPipelineRunning: (v) => set({ pipelineRunning: v }),

  theme: _savedTheme,
  setTheme: (t) => {
    localStorage.setItem('ls-theme', t)
    set({ theme: t })
  },

  dgSettings: DEFAULT_DG_SETTINGS,
  updateDgSettings: (patch) =>
    set((s) => ({ dgSettings: { ...s.dgSettings, ...patch } })),

  sourceLang: 'en',
  setSourceLang: (v) => set({ sourceLang: v }),

  speakers: new Map(),
  _speakerOrder: [],

  speakerColour: (id: string) => {
    const order = get()._speakerOrder
    const idx = order.indexOf(id)
    return SPEAKER_COLOURS[(idx === -1 ? order.length : idx) % SPEAKER_COLOURS.length]
  },

  transcript: [],

  ingestEvent: (event: SpeakerEvent) =>
    set((state) => {
      // ── Update speaker state ──────────────────────────────────────── //
      const speakers = new Map(state.speakers)
      const speakerOrder = [...state._speakerOrder]

      if (!speakerOrder.includes(event.speaker_id)) {
        speakerOrder.push(event.speaker_id)
      }

      const existing = speakers.get(event.speaker_id)
      const newPoint = {
        timestamp: Date.parse(event.timestamp),
        score: event.final_score,
        polarity: event.polarity,
      }

      speakers.set(event.speaker_id, {
        speaker_id: event.speaker_id,
        latest_polarity: event.polarity,
        latest_score: event.final_score,
        dominant_emotion: event.dominant_emotion,
        sentimentHistory: [
          ...(existing?.sentimentHistory.slice(-99) ?? []),
          newPoint,
        ],
      })

      // ── Append to transcript ──────────────────────────────────────── //
      const entry: TranscriptEntry = {
        id: `${event.speaker_id}-${event.timestamp}`,
        speaker_id: event.speaker_id,
        timestamp: event.timestamp,
        text: event.transcript,
        translation: event.translation,
        polarity: event.polarity,
        language: event.language,
      }

      // Deduplicate: skip if an entry with the same id already exists
      // (can happen if multiple WS connections fire the same event)
      if (state.transcript.some((t) => t.id === entry.id)) {
        return { speakers, _speakerOrder: speakerOrder }
      }

      const transcript = [...state.transcript.slice(-199), entry]

      return { speakers, _speakerOrder: speakerOrder, transcript }
    }),

  clearAll: () =>
    set({ speakers: new Map(), transcript: [], _speakerOrder: [] }),
}))
