import {useEffect, useRef, useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode} from 'react'
import {Check} from 'lucide-react'

export function motionReduced() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduce-motion')
}

/** A single, restrained ripple connects a navigation gesture with its destination. */
export function RouteRipple({route}: {route: string}) {
  const [ripple, setRipple] = useState<{key: number; x: number; y: number} | null>(null)
  const origin = useRef({x: window.innerWidth / 2, y: window.innerHeight / 2})
  const previous = useRef(route)
  useEffect(() => {
    const remember = (event: PointerEvent) => {origin.current = {x: event.clientX, y: event.clientY}}
    document.addEventListener('pointerdown', remember, {passive: true})
    return () => document.removeEventListener('pointerdown', remember)
  }, [])
  useEffect(() => {
    if (previous.current === route) return
    previous.current = route
    if (motionReduced()) return
    setRipple({key: Date.now(), ...origin.current})
    const timer = window.setTimeout(() => setRipple(null), 700)
    return () => window.clearTimeout(timer)
  }, [route])
  return ripple ? <div key={ripple.key} className="route-ripple" aria-hidden="true" style={{'--ripple-x': `${ripple.x}px`, '--ripple-y': `${ripple.y}px`} as CSSProperties}/> : null
}

export function FeedbackButton({busy = false, complete = false, children, busyLabel = '正在处理', completeLabel = '已完成', className = '', disabled, ...props}: ButtonHTMLAttributes<HTMLButtonElement> & {busy?: boolean; complete?: boolean; busyLabel?: string; completeLabel?: string; children: ReactNode}) {
  return <button {...props} className={`button feedback-button ${className} ${complete ? 'is-complete' : ''}`} disabled={disabled || busy} aria-busy={busy || undefined}>
    <span key={busy ? 'busy' : complete ? 'complete' : 'idle'} className="feedback-content">{busy ? <><span className="activity-bars" aria-hidden="true"><i/><i/><i/></span>{busyLabel}</> : complete ? <><span className="completion-check"><Check size={18}/></span>{completeLabel}</> : children}</span>
  </button>
}

export function CaptureProgress({fileReady, linked, complete, sampleOnly = false}: {fileReady: boolean; linked: boolean; complete: boolean; sampleOnly?: boolean}) {
  return <ol className="capture-progress" aria-label="本次观察进度">{[
    {label: '选好照片或视频', done: fileReady},
    {label: linked ? '已关联地块' : '地块选填', done: linked},
    {label: complete ? (sampleOnly ? '样本已保存' : '观察已保存') : sampleOnly ? '保存采集样本' : '识别并保存', done: complete},
  ].map((step, index) => <li key={index} className={step.done ? 'is-done' : ''}><span className="progress-check" aria-hidden="true">{step.done ? <Check size={12}/> : index + 1}</span><span>{step.label}</span></li>)}</ol>
}
