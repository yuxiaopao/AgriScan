import {lazy, Suspense, useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent} from 'react'
import {createPortal, flushSync} from 'react-dom'
import {ChevronDown} from 'lucide-react'
import {motionReduced} from './Motion'
import {getServiceBase} from './api'
import {lockBodyScroll} from './overlay'
import type {Detection, User} from './types'
import './floating-assistant.css'

const AssistantPage = lazy(() => import('./AssistantPage'))
const ballWidth = 64, ballHeight = 92
function viewport() {
  const visual = window.visualViewport
  const style = getComputedStyle(document.documentElement)
  return {height: visual?.height ?? window.innerHeight, top: visual?.offsetTop ?? 0, keyboard: window.innerHeight - (visual?.height ?? window.innerHeight) > 150,
    safeTop: parseFloat(style.getPropertyValue('--assistant-safe-top')) || 0, safeBottom: parseFloat(style.getPropertyValue('--assistant-safe-bottom')) || 0}
}
function bounds() {
  const view = viewport(), width = document.documentElement.clientWidth, frame = Math.min(width, 480), left = (width - frame) / 2
  const minY = view.top + 80 + view.safeTop
  const height = document.querySelector('.mobile-assistant-ball')?.getBoundingClientRect().height || ballHeight
  const navigationTop = document.querySelector('.bottom-tabs')?.getBoundingClientRect().top
  const bottom = Math.min(view.top + view.height - view.safeBottom - 12, navigationTop ?? Infinity)
  return {minX: left + 12, maxX: left + frame - ballWidth - 12, minY, maxY: Math.max(minY, bottom - height - 8)}
}
function defaultPosition() {const area = bounds(); return {x: area.maxX, y: area.maxY}}

export default function FloatingAssistant({user, record, onHandled, open, onOpen, onClose}: {
  user: User; record: Detection | null; onHandled: () => void; open: boolean; onOpen: () => void; onClose: () => void
}) {
  const [activated, setActivated] = useState(open)
  const [present, setPresent] = useState(open)
  const [position, setPosition] = useState(defaultPosition)
  const [view, setView] = useState(viewport)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [unread, setUnread] = useState(false)
  const ball = useRef<HTMLButtonElement>(null), panel = useRef<HTMLElement>(null)
  const openRef = useRef(open), closeRef = useRef(onClose), positionRef = useRef(position)
  const dock = useRef({side: 'right', ratio: 1, manual: false})
  const gesture = useRef<{id: number; x: number; y: number; originX: number; originY: number; moved: boolean} | null>(null)
  const ignoreClick = useRef(false)
  openRef.current = open; closeRef.current = onClose; positionRef.current = position
  const onReply = useCallback(() => {if (!openRef.current) setUnread(true)}, [])

  useEffect(() => {
    let frame = 0
    const resize = () => {
      setView(viewport())
      const area = bounds()
      const next = {x: dock.current.side === 'left' ? area.minX : area.maxX, y: area.minY + (area.maxY - area.minY) * dock.current.ratio}
      // Keep compact controls such as preference switches reachable at the default dock.
      // Large rows remain usable across their full width; manual placement is respected.
      if(!dock.current.manual) {
        const height=ball.current?.getBoundingClientRect().height || ballHeight
        const controls=Array.from(document.querySelectorAll<HTMLElement>('.app-main button,.app-main input,.app-main select,.app-main textarea'))
          .filter(element=>element.getClientRects().length&&!element.closest('[hidden]'))
          .map(element=>element.getBoundingClientRect()).filter(rect=>rect.width>0&&rect.width<=120)
        const obstructed=(point:{x:number;y:number})=>controls.some(rect=>point.x<rect.right+8&&point.x+ballWidth>rect.left-8&&point.y<rect.bottom+8&&point.y+height>rect.top-8)
        if(obstructed(next)) {
          const opposite={...next,x:next.x===area.maxX?area.minX:area.maxX}
          if(!obstructed(opposite))next.x=opposite.x
          else for(let y=next.y-16;y>=area.minY;y-=16){const candidate={...next,y};if(!obstructed(candidate)){next.y=y;break}}
          dock.current={side:next.x===area.minX?'left':'right',ratio:area.maxY===area.minY?1:(next.y-area.minY)/(area.maxY-area.minY),manual:false}
        }
      }
      const before=ball.current?.getBoundingClientRect()
      setPosition(next)
      cancelAnimationFrame(frame)
      frame=requestAnimationFrame(()=>{const after=ball.current?.getBoundingClientRect();if(before&&after&&!motionReduced()&&!gesture.current&&(Math.abs(before.left-after.left)>1||Math.abs(before.top-after.top)>1))ball.current?.animate([{transform:`translate(${before.left-after.left}px,${before.top-after.top}px)`},{transform:'translate(0,0)'}],{duration:350,easing:'cubic-bezier(.22,1,.36,1)'})})
    }
    const queueResize=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(resize)}
    window.addEventListener('resize', resize)
    window.addEventListener('hashchange',queueResize)
    window.addEventListener('scroll',queueResize,{passive:true})
    window.visualViewport?.addEventListener('resize', resize)
    window.visualViewport?.addEventListener('scroll', resize)
    const observer = new ResizeObserver(resize)
    if(ball.current)observer.observe(ball.current)
    const navigation=document.querySelector('.bottom-tabs')
    if(navigation)observer.observe(navigation)
    const content=document.querySelector('.app-main')
    if(content)observer.observe(content)
    resize()
    return () => {cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('resize', resize);window.removeEventListener('hashchange',queueResize);window.removeEventListener('scroll',queueResize);window.visualViewport?.removeEventListener('resize', resize); window.visualViewport?.removeEventListener('scroll', resize)}
  }, [])

  useEffect(() => {
    if (open) {setActivated(true); setPresent(true); setUnread(false); return}
    const timer = window.setTimeout(() => setPresent(false), motionReduced() ? 0 : 250)
    return () => window.clearTimeout(timer)
  }, [open, activated])
  useEffect(() => {if (activated && !open && !present) ball.current?.focus({preventScroll: true})}, [activated, open, present])

  useEffect(() => {
    if (!open || !present) return
    const unlock = lockBodyScroll()
    const frame = requestAnimationFrame(() => panel.current?.focus({preventScroll: true}))
    const handleKey = (event: KeyboardEvent) => {
      const dialogs = document.querySelectorAll('[role="dialog"]')
      if (dialogs[dialogs.length - 1] !== panel.current) return
      if (event.key === 'Escape') {event.preventDefault(); closeRef.current(); return}
      if (event.key !== 'Tab') return
      const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), textarea:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]') ?? [])
      const first = items[0], last = items[items.length - 1]
      if (!items.length) {event.preventDefault(); panel.current?.focus(); return}
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {event.preventDefault(); last.focus()}
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) {event.preventDefault(); first.focus()}
    }
    document.addEventListener('keydown', handleKey)
    return () => {cancelAnimationFrame(frame); unlock(); document.removeEventListener('keydown', handleKey)}
  }, [open, present])

  function move(event: ReactPointerEvent<HTMLButtonElement>) {
    const active = gesture.current
    if (!active || active.id !== event.pointerId) return
    const dx = event.clientX - active.x, dy = event.clientY - active.y
    if (!active.moved && Math.hypot(dx, dy) < 6) return
    active.moved = true; setDragging(true)
    const area = bounds()
    const next = {x: Math.max(area.minX, Math.min(area.maxX, active.originX + dx)), y: Math.max(area.minY, Math.min(area.maxY, active.originY + dy))}
    positionRef.current = next; setPosition(next)
  }
  function finish(event: ReactPointerEvent<HTMLButtonElement>) {
    const active = gesture.current
    if (!active || active.id !== event.pointerId) return
    ignoreClick.current = active.moved
    if (active.moved) {
      const area = bounds(), current = positionRef.current
      const left = current.x < (area.minX + area.maxX) / 2
      dock.current = {side: left ? 'left' : 'right', ratio: area.maxY === area.minY ? 1 : (current.y - area.minY) / (area.maxY - area.minY), manual: true}
      const before = ball.current?.getBoundingClientRect()
      flushSync(() => {setPosition({x: left ? area.minX : area.maxX, y: current.y}); setDragging(false)})
      const after = ball.current?.getBoundingClientRect()
      if (before && after && !motionReduced()) ball.current?.animate([
        {transform: `translate(${before.left - after.left}px,${before.top - after.top}px) scale(1.06)`}, {transform: 'translate(0,0) scale(1)'},
      ], {duration: 500, easing: 'cubic-bezier(.22,1,.36,1)'})
    }
    gesture.current = null; setDragging(false)
  }
  const compact = view.keyboard || view.height < 480
  const bottomGap = compact ? 8 : 104 + view.safeBottom
  const height = Math.max(0, Math.min(650, view.height - bottomGap - 16 - (compact ? 0 : view.safeTop)))
  const top = view.top + Math.max(8, view.height - bottomGap - height)

  return createPortal(<>
    <button ref={ball} className={`mobile-assistant-ball ${dragging ? 'is-dragging' : ''} ${present ? 'is-hidden' : ''} ${busy ? 'is-thinking' : ''}`} style={{left: position.x, top: position.y}}
      type="button" aria-label={unread ? '打开小禾悬浮助手，有新回复' : '打开小禾悬浮助手'} aria-haspopup="dialog" aria-expanded={open} aria-controls="mobile-assistant-window" aria-hidden={present || undefined} tabIndex={present ? -1 : 0}
      title="点击和小禾聊天，拖动可调整位置" onClick={() => {if (ignoreClick.current) {ignoreClick.current = false; return}; onOpen()}}
      onPointerDown={event => {if (event.button !== 0) return; ignoreClick.current = false; gesture.current = {id: event.pointerId, x: event.clientX, y: event.clientY, originX: position.x, originY: position.y, moved: false}; event.currentTarget.setPointerCapture(event.pointerId)}}
      onPointerMove={move} onPointerUp={finish} onPointerCancel={event => {finish(event); ignoreClick.current = true}}
      onKeyDown={event => {if (!event.key.startsWith('Arrow')) return; event.preventDefault(); const area = bounds(); const x = event.key === 'ArrowLeft' ? area.minX : event.key === 'ArrowRight' ? area.maxX : position.x; const y = Math.max(area.minY, Math.min(area.maxY, position.y + (event.key === 'ArrowUp' ? -32 : event.key === 'ArrowDown' ? 32 : 0))); dock.current = {side: x === area.minX ? 'left' : 'right', ratio: area.maxY === area.minY ? 1 : (y - area.minY) / (area.maxY - area.minY), manual: true}; setPosition({x, y})}}>
      <span className="mobile-assistant-orb"><span className="assistant-orb-halo"/><img src="/images/xiaohe.png" alt="" draggable={false}/><i className={unread ? 'has-reply' : ''}/></span><span className="assistant-ball-label">{busy ? '思考中' : unread ? '有新回复' : '小禾'}</span>
    </button>
    {activated && <div className={`mobile-assistant-layer ${open ? 'is-open' : 'is-closing'}`} hidden={!present}>
      <button className="mobile-assistant-backdrop" aria-label="收起小禾悬浮窗" tabIndex={-1} onClick={onClose}/>
      <section ref={panel} id="mobile-assistant-window" className={`mobile-assistant-window ${view.height < 360 ? 'is-compact' : ''}`} style={{top, height}} role={open ? 'dialog' : undefined} aria-modal={open || undefined} aria-label="小禾悬浮助手" aria-hidden={!open || undefined} inert={!open || undefined} tabIndex={-1}>
        <Suspense fallback={<div className="assistant-floating-loading"><header><strong>小禾</strong><button className="icon-button" aria-label="收起小禾" onClick={onClose}><ChevronDown size={22}/></button></header><p role="status">正在找回你的田间对话…</p></div>}><AssistantPage key={`${getServiceBase()}:${user.username}`} user={user} record={record} onHandled={onHandled} onMinimize={onClose} onBusyChange={setBusy} onReply={onReply} visible={open}/></Suspense>
      </section>
    </div>}
  </>, document.body)
}
