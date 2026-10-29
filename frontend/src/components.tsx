import {useEffect, useRef, useState, type ReactNode} from 'react'
import {createPortal} from 'react-dom'
import {ArrowUpRight, Check, CircleAlert, Clock3, Leaf, ScanLine, X} from 'lucide-react'
import {motionCurve, reducedMotion} from './motion'
import type {Detection, DetectionStatus} from './types'
import {apiResourceUrl, getToken} from './api'

const modalLocks = new Set<symbol>()
let previousBodyOverflow = ''

export const statusLabels: Record<DetectionStatus, string> = {healthy: '健康', attention: '需关注', awaiting_model: '等待模型', queued: '排队中', processing: '检测中', failed: '检测失败'}
export function Badge({status}: {status: DetectionStatus}) {
  const Icon = status === 'healthy' ? Check : status === 'attention' || status === 'failed' ? CircleAlert : Clock3
  return <span className={`badge ${status}`}><Icon size={12}/>{statusLabels[status]}</span>
}
export function CropIcon({crop, size = 36}: {crop: string; size?: number}) {
  const colors: Record<string, string> = {番茄: '#ee886c', 水稻: '#78a477', 玉米: '#d3ab51', 小麦: '#c19a62', 黄瓜: '#4e9174'}
  return <span className="crop-icon" style={{width: size, height: size, color: colors[crop] ?? '#75a180', background: `${colors[crop] ?? '#75a180'}15`}}><Leaf size={size * .48}/></span>
}
export function Empty({title, description, action}: {title: string; description: string; action?: ReactNode}) {
  return <div className="empty"><div className="empty-icon"><ScanLine size={30}/></div><h3>{title}</h3><p>{description}</p>{action}</div>
}
export function Loading() { return <div className="workspace-skeleton" role="status" aria-label="正在读取田间数据"><span className="skeleton-line skeleton-heading"/><div className="skeleton-stats">{[0,1,2,3].map(item => <span className="skeleton-card" key={item}><i/><i/></span>)}</div><span className="skeleton-chart"/><span className="sr-only">正在读取田间数据…</span></div> }
export function Modal({title, children, onClose, wide = false}: {title: string; children: ReactNode; onClose: () => void; wide?: boolean}) {
  const ref = useRef<HTMLDivElement>(null)
  const closeRef = useRef(onClose)
  const closing = useRef(false)
  closeRef.current = onClose
  function dismiss() {
    if (closing.current) return
    const root = ref.current
    if (!root || reducedMotion()) {closeRef.current(); return}
    closing.current = true
    const panel = root.animate([{transform: 'translateY(0) scale(1)', opacity: 1}, {transform: 'translateY(16px) scale(.98)', opacity: 0}], {duration: 220, easing: motionCurve})
    void panel.finished.then(() => {closing.current = false; closeRef.current()}, () => {closing.current = false})
  }
  const dismissRef = useRef(dismiss)
  dismissRef.current = dismiss
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const root = ref.current
    const focusables = () => Array.from(root?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, textarea, a[href], [tabindex="0"]') ?? [])
    focusables()[0]?.focus()
    const onKey = (event: KeyboardEvent) => {
      const dialogs = document.querySelectorAll('[role="dialog"]')
      if (dialogs[dialogs.length - 1] !== root) return
      if (event.key === 'Escape') {event.preventDefault(); event.stopPropagation(); dismissRef.current()}
      if (event.key === 'Tab') {
        const list = focusables(), first = list[0], last = list[list.length - 1]
        if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus()}
        if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus()}
      }
    }
    document.addEventListener('keydown', onKey)
    const lock = Symbol('modal')
    if (!modalLocks.size) previousBodyOverflow = document.body.style.overflow
    modalLocks.add(lock)
    document.body.style.overflow = 'hidden'
    return () => {document.removeEventListener('keydown', onKey); modalLocks.delete(lock); if (!modalLocks.size) document.body.style.overflow = previousBodyOverflow; if (previous?.isConnected) previous.focus()}
  }, [])
  return createPortal(<div className={`modal-overlay ${import.meta.env.VITE_APP_SURFACE === 'admin' ? 'admin-dialog-surface' : ''}`} onMouseDown={event => {if (event.target === event.currentTarget) dismiss()}}>
    <div ref={ref} className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-head"><h2>{title}</h2><button className="icon-button" onClick={dismiss} aria-label="关闭弹窗"><X size={20}/></button></div>
      {children}
    </div>
  </div>, document.body)
}
export function DetectionTable({records, onSelect, selected, onToggle, onToggleAll}: {records: Detection[]; onSelect: (record: Detection) => void; selected?: Set<string>; onToggle?: (id: string) => void; onToggleAll?: () => void}) {
  const all = records.length > 0 && records.every(record => selected?.has(record.id))
  const some = records.some(record => selected?.has(record.id))
  return <div className="table-scroll"><table><thead><tr>{selected && <th className="selection-cell"><input type="checkbox" aria-label="全选当前页记录" checked={all} ref={node => {if (node) node.indeterminate = some && !all}} onChange={onToggleAll}/></th>}<th>检测样本</th><th>所属地块</th><th>检测结果</th><th>检测时间</th><th><span className="sr-only">查看</span></th></tr></thead><tbody>
    {records.map(record => <tr key={record.id} className={selected?.has(record.id) ? 'record-selected' : undefined} onClick={() => onSelect(record)}>
      {selected && <td className="selection-cell" onClick={event => event.stopPropagation()}><input type="checkbox" aria-label={`选择${record.name}`} checked={selected.has(record.id)} onChange={() => onToggle?.(record.id)}/></td>}
      <td><div className="sample-cell">{record.image_url ? <SecureImage className="sample-thumb" url={record.image_url} alt={record.crop}/> : <CropIcon crop={record.crop}/>}<div><button className="table-name" onClick={event => {event.stopPropagation(); onSelect(record)}}>{record.name}</button><span className="subtext">{record.crop}<span className="dot-separator">·</span>{record.is_demo ? '示例样本' : '上传样本'}</span></div></div></td>
      <td>{record.plot_name || '未关联地块'}</td><td><Badge status={record.status}/></td><td className="date-cell">{new Date(record.created_at).toLocaleString('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'})}</td>
      <td><ArrowUpRight size={16} className="table-arrow"/></td>
    </tr>)}
  </tbody></table></div>
}

export function SecureImage({url, alt, className}: {url: string; alt: string; className?: string}) {
  const [source, setSource] = useState('')
  const [failed, setFailed] = useState(false)
  const token = getToken()
  useEffect(() => {
    let alive = true
    let objectUrl = ''
    setSource(''); setFailed(false)
    const controller = new AbortController()
    const resolved = new URL(apiResourceUrl(url), window.location.origin)
    const headers = token && resolved.origin === window.location.origin ? {Authorization: `Bearer ${token}`} : undefined
    fetch(resolved, {headers, cache: 'no-store', signal: controller.signal})
      .then(response => {if (!response.ok) throw new Error(); return response.blob()})
      .then(blob => {objectUrl = URL.createObjectURL(blob); if (alive) setSource(objectUrl); else URL.revokeObjectURL(objectUrl)})
      .catch(() => {if (alive) setFailed(true)})
    return () => {alive = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl)}
  }, [url, token])
  return failed ? <span className={className} role="img" aria-label={`${alt}，图片暂时无法加载`} title="图片暂时无法加载"><Leaf size={20}/></span> : source ? <img className={className} src={source} alt={alt}/> : <span className={`${className || ''} image-skeleton`} role="status" aria-label="正在加载图片"/>
}
