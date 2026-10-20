// ─── Domain types matching backend Pydantic schemas ─────────────────── //

export interface SpeakerEvent {
  event_type: 'speaker_event'
  timestamp: string
  speaker_id: string
  transcript: string
  language: string
  translation: string | null
  polarity: 'positive' | 'negative' | 'neutral'
  final_score: number
  text_score: number | null
  acoustic_score: number | null
  dominant_emotion: string | null
  emotions: Record<string, number>
  confidence: number
}

export interface PipelineStatus {
  running: boolean
  device: string
  whisper_model: string
  translate_enabled: boolean
}

// ─── Store types ─────────────────────────────────────────────────────── //

export interface TranscriptEntry {
  id: string
  speaker_id: string
  timestamp: string
  text: string
  translation: string | null
  polarity: SpeakerEvent['polarity']
  language: string
}

export interface SentimentPoint {
  timestamp: number   // unix ms
  score: number
  polarity: SpeakerEvent['polarity']
}

export interface SpeakerState {
  speaker_id: string
  latest_polarity: SpeakerEvent['polarity']
  latest_score: number
  dominant_emotion: string | null
  sentimentHistory: SentimentPoint[]
}

// ─── Upload / Session types ───────────────────────────────────────────── //

export type UploadStatus = 'uploaded' | 'processing' | 'completed' | 'failed'
export type SessionStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type SessionType = 'live' | 'upload'

export interface FileMetadata {
  original_name: string
  stored_name: string
  size_bytes: number
  duration_seconds: number | null
  sample_rate: number | null
  channels: number | null
  format: string | null
  content_type: string
}

export interface SessionSummary {
  event_count: number
  speaker_count: number
  total_duration_seconds: number
  dominant_emotion: string | null
  avg_sentiment_score: number
  polarity_distribution: Record<string, number>
  languages: string[]
}

export interface Session {
  session_id: string
  type: SessionType
  status: SessionStatus
  created_at: string
  updated_at: string
  completed_at: string | null
  file: FileMetadata | null
  summary: SessionSummary | null
  error: string | null
  tags: string[]
}

export interface UploadRecord {
  session_id: string
  original_filename: string
  content_type: string
  size_bytes: number
  storage_path: string
  status: UploadStatus
  uploaded_at: string
  processing_started_at: string | null
  processing_completed_at: string | null
  error: string | null
}

export interface SessionEvent {
  session_id: string
  event_index: number
  timestamp_utc: string
  offset_seconds: number
  speaker_id: string
  transcript: string
  language: string
  translation: string | null
  polarity: 'positive' | 'negative' | 'neutral'
  final_score: number
  text_score: number | null
  acoustic_score: number | null
  dominant_emotion: string | null
  emotions: Record<string, number>
  confidence: number
}

export interface SpeakerStats {
  session_id: string
  speaker_id: string
  total_utterances: number
  total_words: number
  total_speaking_seconds: number
  avg_sentiment_score: number
  dominant_emotion: string | null
  emotion_counts: Record<string, number>
  polarity_counts: Record<string, number>
  languages: string[]
}

// ─── Auth types ───────────────────────────────────────────────────────── //

export type UserRole = 'admin' | 'user'

export interface AuthUser {
  username: string
  role: UserRole
  full_name: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  username: string
  role: UserRole
}

export interface UserRecord {
  username: string
  role: UserRole
  full_name: string | null
  is_active: boolean
  created_at: string
  created_by: string | null
}
