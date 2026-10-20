import { useEffect, useRef, useState } from 'react'

/**
 * Returns a live 0–1 audio level from the default microphone.
 * Only active when `enabled` is true (i.e. pipeline is running).
 * Falls back to 0 if mic permission is denied.
 */
export function useAudioLevel(enabled: boolean): number {
  const [level, setLevel] = useState(0)
  const rafRef = useRef<number | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)

  useEffect(() => {
    if (!enabled) {
      setLevel(0)
      return
    }

    let alive = true

    navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .then((stream) => {
        if (!alive) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        const ctx = new AudioContext()
        ctxRef.current = ctx
        const source = ctx.createMediaStreamSource(stream)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        source.connect(analyser)
        analyserRef.current = analyser

        const buf = new Uint8Array(analyser.frequencyBinCount)

        function tick() {
          if (!alive) return
          analyser.getByteTimeDomainData(buf)
          // RMS of the waveform
          let sum = 0
          for (let i = 0; i < buf.length; i++) {
            const v = (buf[i] - 128) / 128
            sum += v * v
          }
          const rms = Math.sqrt(sum / buf.length)
          setLevel(Math.min(rms * 5, 1)) // amplify & clamp to [0,1]
          rafRef.current = requestAnimationFrame(tick)
        }
        rafRef.current = requestAnimationFrame(tick)
      })
      .catch(() => {
        // Permission denied — leave level at 0
      })

    return () => {
      alive = false
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      streamRef.current?.getTracks().forEach((t) => t.stop())
      ctxRef.current?.close()
      streamRef.current = null
      ctxRef.current = null
      analyserRef.current = null
      setLevel(0)
    }
  }, [enabled])

  return level
}
