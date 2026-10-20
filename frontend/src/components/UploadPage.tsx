/**
 * components/UploadPage.tsx
 * File upload UI + polling for processing status.
 */

import { useRef, useState } from 'react'
import { uploadFile } from '../lib/api'

const ALLOWED = '.wav,.mp3,.flac,.ogg,.m4a,.aac,.mp4'

function fmt(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [state, setState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleFile = (f: File) => {
    setFile(f)
    setState('idle')
    setSessionId(null)
    setError(null)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const handleUpload = async () => {
    if (!file) return
    setState('uploading')
    setError(null)
    try {
      const res = await uploadFile(file)
      setSessionId(res.session_id)
      setState('done')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-6">
      <div>
        <h2 className="text-lg font-semibold">Upload Audio File</h2>
        <p className="text-sm text-slate-400 mt-1">
          Supported formats: WAV, MP3, FLAC, OGG, M4A · Max 500 MB
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`
          border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors
          ${dragOver ? 'border-indigo-400 bg-indigo-950/30' : 'border-border hover:border-indigo-500 hover:bg-indigo-950/10'}
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED}
          className="hidden"
          onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        <div className="text-4xl mb-3">🎵</div>
        {file ? (
          <div>
            <p className="font-medium text-slate-200">{file.name}</p>
            <p className="text-sm text-slate-400 mt-1">{fmt(file.size)}</p>
          </div>
        ) : (
          <div>
            <p className="text-slate-300">Drop an audio file here or click to browse</p>
            <p className="text-xs text-slate-500 mt-2">{ALLOWED}</p>
          </div>
        )}
      </div>

      {/* Upload button */}
      {file && state !== 'done' && (
        <button
          onClick={handleUpload}
          disabled={state === 'uploading'}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold rounded-lg px-6 py-3 transition-colors"
        >
          {state === 'uploading' ? 'Uploading…' : 'Start Processing'}
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-950/40 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Success */}
      {state === 'done' && sessionId && (
        <div className="bg-emerald-950/40 border border-emerald-700 rounded-xl p-5">
          <div className="flex items-center gap-2 text-emerald-400 font-semibold mb-2">
            <span>✓</span> Processing started
          </div>
          <p className="text-sm text-slate-300 mb-3">
            Your file is being processed. Track progress in the{' '}
            <span className="text-indigo-400">Sessions</span> tab.
          </p>
          <div className="bg-slate-800 rounded px-3 py-2 font-mono text-xs text-slate-400 break-all">
            session_id: {sessionId}
          </div>
        </div>
      )}
    </div>
  )
}
