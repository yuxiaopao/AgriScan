import {useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode} from 'react'
import {Check, Download} from 'lucide-react'

export const motionCurve = 'cubic-bezier(0.22, 1, 0.36, 1)'
export function reducedMotion() {
  return document.documentElement.classList.contains('reduce-motion') || window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** A single observer handles newly mounted pages without hiding content before JS loads. */
export function MotionSurface({children, className = '', page}: {children: ReactNode; className?: string; page: string}) {
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!root.current || reducedMotion()) return
    const arrivingWithTransition = Boolean(document.documentElement.dataset.routeTransition)
    const animations = new Set<Animation>()
    const seen = new WeakSet<Element>()
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return
        const node = entry.target as HTMLElement
        const animation = node.animate([{opacity: 0, transform: 'translateY(24px)'}, {opacity: 1, transform: 'translateY(0)'}], {
          duration: 650, delay: Number(node.dataset.motionDelay || 0), easing: motionCurve,
        })
        animations.add(animation)
        void animation.finished.then(() => animations.delete(animation), () => animations.delete(animation))
        observer.unobserve(node)
      })
    }, {threshold: .06})
    const observeContent = () => root.current?.querySelectorAll<HTMLElement>('.panel, .stat-card, .welcome-banner, .crop-room, .page-intro, .knowledge-banner, .notice').forEach((node, index) => {
      if (seen.has(node) || document.documentElement.dataset.routeTransition) return
      seen.add(node)
      const rect = node.getBoundingClientRect()
      if (arrivingWithTransition && rect.top < window.innerHeight && rect.bottom > 0) return
      node.dataset.motionDelay = String(Math.min(index % 4 * 60, 180))
      observer.observe(node)
    })
    observeContent()
    const contentObserver = new MutationObserver(observeContent)
    contentObserver.observe(root.current, {childList: true, subtree: true})
    window.addEventListener('agriscan-route-settled', observeContent)
    const cancelIfReduced = () => {
      if (reducedMotion()) {observer.disconnect(); contentObserver.disconnect(); animations.forEach(animation => animation.cancel())}
    }
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    media.addEventListener('change', cancelIfReduced)
    const preference = new MutationObserver(cancelIfReduced)
    preference.observe(document.documentElement, {attributes: true, attributeFilter: ['class']})
    return () => {observer.disconnect(); contentObserver.disconnect(); preference.disconnect(); window.removeEventListener('agriscan-route-settled', observeContent); media.removeEventListener('change', cancelIfReduced); animations.forEach(animation => animation.cancel())}
  }, [page])
  return <div ref={root} className={`motion-surface ${className}`}>{children}</div>
}

/** A bounded, interruptible transition. The circle never intercepts input. */
export function revealCropTheme(color: string, origin?: {x: number; y: number}) {
  if (reducedMotion()) return
  document.querySelectorAll('.crop-theme-ripple').forEach(node => node.remove())
  const x = origin?.x ?? window.innerWidth * .7, y = origin?.y ?? 180
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
  const circle = document.createElement('span')
  circle.className = 'crop-theme-ripple'
  Object.assign(circle.style, {width: `${radius * 2}px`, height: `${radius * 2}px`, left: `${x - radius}px`, top: `${y - radius}px`, background: color})
  document.body.append(circle)
  const animation = circle.animate([
    {transform: 'scale(0)', opacity: .85, offset: 0},
    {transform: 'scale(1)', opacity: .4, offset: .68},
    {transform: 'scale(1)', opacity: 0, offset: 1},
  ], {duration: 720, easing: motionCurve})
  void animation.finished.then(() => circle.remove(), () => circle.remove())
}

export function FeedbackButton({onAction, children, doneLabel = '已完成', className = 'button outline', ...props}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & {
  onAction: () => void | Promise<void>; children: ReactNode; doneLabel?: string
}) {
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const mounted = useRef(true)
  const inFlight = useRef(false)
  useEffect(() => {mounted.current = true; return () => {mounted.current = false; clearTimeout(timer.current)}}, [])
  async function run() {
    if (inFlight.current) return
    inFlight.current = true; setState('busy')
    try {
      await onAction()
      if (mounted.current) {
        setState('done')
        timer.current = setTimeout(() => {if (mounted.current) setState('idle')}, 2400)
      }
    } finally {inFlight.current = false; if (mounted.current) setState(current => current === 'busy' ? 'idle' : current)}
  }
  return <button {...props} type={props.type || 'button'} className={`${className} feedback-button ${state}`} disabled={props.disabled || state !== 'idle'} aria-busy={state === 'busy'} onClick={() => {void run().catch(() => {if (mounted.current) setState('idle')})}}>
    <span className="feedback-label">{children}</span><span className="feedback-complete" aria-hidden="true"><Check size={16}/>{doneLabel}</span>
    <span className="sr-only" role="status">{state === 'done' ? doneLabel : state === 'busy' ? '正在处理' : ''}</span>
  </button>
}

export function ExportButton({onAction, disabled, children = '导出记录'}: {onAction: () => void; disabled?: boolean; children?: ReactNode}) {
  return <FeedbackButton onAction={onAction} disabled={disabled} doneLabel="已生成文件"><Download size={15}/>{children}</FeedbackButton>
}
