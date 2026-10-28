import {useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent, type PointerEvent, type RefObject} from 'react'

interface Rect {x: number; y: number; width: number; height: number}
interface Gesture {pointer: number; origin: Rect; x: number; y: number; resize: boolean}
const margin = 12
function fit(rect: Rect): Rect {
  const width = Math.min(Math.max(320, rect.width), window.innerWidth - margin * 2)
  const height = Math.min(Math.max(360, rect.height), window.innerHeight - margin * 2)
  return {width, height, x: Math.max(margin, Math.min(rect.x, window.innerWidth - width - margin)),
    y: Math.max(margin, Math.min(rect.y, window.innerHeight - height - margin))}
}
export function useFloatingPosition(open: boolean) {
  const panel = useRef<HTMLElement>(null)
  const [rect, setRect] = useState<Rect | null>(null)
  const [maximized, setMaximized] = useState(false)
  const restore = useRef<Rect | null>(null)
  const gesture = useRef<Gesture | null>(null)
  function current(): Rect {
    const bounds = panel.current?.getBoundingClientRect()
    return bounds ? {x: bounds.left, y: bounds.top, width: bounds.width, height: bounds.height}
      : fit({x: window.innerWidth - 428, y: window.innerHeight - 604, width: 400, height: 580})
  }
  useEffect(() => {
    if (!open) {gesture.current = null; return}
    function adjust() {
      if (maximized) setRect(fit({x: margin, y: margin, width: window.innerWidth, height: window.innerHeight}))
      else setRect(previous => fit(previous ?? current()))
    }
    const frame = requestAnimationFrame(adjust)
    window.addEventListener('resize', adjust)
    return () => {cancelAnimationFrame(frame); window.removeEventListener('resize', adjust)}
  }, [open, maximized])
  function toggleMaximize() {
    gesture.current = null
    if (maximized) setRect(fit(restore.current ?? current()))
    else {
      restore.current = current()
      setRect(fit({x: margin, y: margin, width: window.innerWidth, height: window.innerHeight}))
    }
    setMaximized(!maximized)
  }
  function compact() {
    gesture.current = null
    setMaximized(false)
    setRect(fit({...current(), width: 360, height: 440}))
  }
  function start(event: PointerEvent<HTMLElement>, resize: boolean) {
    if (maximized || event.button !== 0 || (!resize && (event.target as HTMLElement).closest('button'))) return
    event.preventDefault()
    gesture.current = {pointer: event.pointerId, origin: current(), x: event.clientX, y: event.clientY, resize}
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function move(event: PointerEvent<HTMLElement>) {
    const start = gesture.current
    if (!start || start.pointer !== event.pointerId) return
    const dx = event.clientX - start.x, dy = event.clientY - start.y
    setRect(fit(start.resize ? {...start.origin,
      width: Math.min(start.origin.width + dx, window.innerWidth - start.origin.x - margin),
      height: Math.min(start.origin.height + dy, window.innerHeight - start.origin.y - margin)}
      : {...start.origin, x: start.origin.x + dx, y: start.origin.y + dy}))
  }
  function end(event: PointerEvent<HTMLElement>) {
    gesture.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }
  function keyboard(event: KeyboardEvent<HTMLElement>, resize: boolean) {
    if (maximized || event.target !== event.currentTarget || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
    event.preventDefault()
    const step = event.shiftKey ? 40 : 16
    const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0
    const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0
    const old = current()
    setRect(fit(resize ? {...old, width: old.width + dx, height: old.height + dy} : {...old, x: old.x + dx, y: old.y + dy}))
  }
  const handlers = (resize: boolean) => ({onPointerDown: (e: PointerEvent<HTMLElement>) => start(e, resize),
    onPointerMove: move, onPointerUp: end, onPointerCancel: end,
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => keyboard(e, resize)})
  const style: CSSProperties | undefined = rect ? {left: rect.x, top: rect.y, width: rect.width, height: rect.height, right: 'auto', bottom: 'auto'} : undefined
  return {panel, style, maximized, toggleMaximize, compact, dragHandlers: handlers(false), resizeHandlers: handlers(true)}
}

export function useLauncherPosition(element: RefObject<HTMLButtonElement | null>, shown: boolean) {
  const [position, setPosition] = useState<{x: number; y: number} | null>(null)
  const gesture = useRef<{pointer: number; x: number; y: number; origin: DOMRect} | null>(null)
  const dragged = useRef(false)
  function fitPosition(x: number, y: number, bounds: DOMRect) {
    return {x: Math.max(margin, Math.min(x, window.innerWidth - bounds.width - margin)),
      y: Math.max(margin, Math.min(y, window.innerHeight - bounds.height - margin))}
  }
  useEffect(() => {
    if (!shown) {gesture.current = null; return}
    const adjust = () => {
      const bounds = element.current?.getBoundingClientRect()
      if (bounds) setPosition(old => old ? fitPosition(old.x, old.y, bounds) : null)
    }
    const frame = requestAnimationFrame(adjust)
    window.addEventListener('resize', adjust)
    return () => {cancelAnimationFrame(frame); window.removeEventListener('resize', adjust)}
  }, [shown, element])
  function start(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || !event.isPrimary) return
    dragged.current = false
    gesture.current = {pointer: event.pointerId, x: event.clientX, y: event.clientY,
      origin: event.currentTarget.getBoundingClientRect()}
    if (event.pointerType !== 'touch') event.currentTarget.setPointerCapture(event.pointerId)
  }
  function move(event: PointerEvent<HTMLButtonElement>) {
    const start = gesture.current
    if (!start || start.pointer !== event.pointerId) return
    const dx = event.clientX - start.x, dy = event.clientY - start.y
    if (!dragged.current && Math.hypot(dx, dy) < 5) return
    dragged.current = true
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.setPointerCapture(event.pointerId)
    setPosition(fitPosition(start.origin.left + dx, start.origin.top + dy, start.origin))
  }
  function end(event: PointerEvent<HTMLButtonElement>) {
    if (gesture.current?.pointer !== event.pointerId) return
    gesture.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (event.type === 'pointerup' && event.pointerType === 'touch' && !dragged.current) {
      event.preventDefault()
      event.currentTarget.click()
    }
  }
  function consumeClick(event: MouseEvent<HTMLButtonElement>) {
    const suppress = dragged.current && event.detail !== 0
    dragged.current = false
    if (suppress) {event.preventDefault(); event.stopPropagation()}
    return suppress
  }
  function keyboard(event: KeyboardEvent<HTMLButtonElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
    event.preventDefault()
    const bounds = event.currentTarget.getBoundingClientRect(), step = event.shiftKey ? 40 : 16
    setPosition(fitPosition(bounds.left + (event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0),
      bounds.top + (event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0), bounds))
  }
  const style: CSSProperties | undefined = position ? {left: position.x, top: position.y, right: 'auto', bottom: 'auto'} : undefined
  return {style, consumeClick, handlers: {onPointerDown: start, onPointerMove: move, onPointerUp: end,
    onPointerCancel: end, onLostPointerCapture: (event: PointerEvent<HTMLButtonElement>) => {
      if (event.target === event.currentTarget) end(event)
    }, onKeyDown: keyboard}}
}
