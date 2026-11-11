import {useEffect, useRef, useState, type CSSProperties, type ReactNode} from 'react'
import {Check, ChevronRight, Leaf, LoaderCircle, MessageCircle, ShieldCheck, X} from 'lucide-react'
import {createPortal} from 'react-dom'
import {getServiceBase, getToken, mediaUrl} from './api'
import {confidence} from './hooks'
import type {Detection} from './types'
import {cropThemes} from './cropThemes'
import {motionReduced} from './Motion'
import {lockBodyScroll} from './overlay'
import {IpIcon} from './IpIcon'
import {ModelVerification} from './ModelVerification'

export function Art({src, alt, className = ''}: {src: string; alt: string; className?: string}) {
  return <img src={src} alt={alt} className={className} draggable={false} onError={event => {if (!event.currentTarget.src.endsWith('/images/xiaohe.png')) event.currentTarget.src = '/images/xiaohe.png'}}/>
}
export function Loading({text = '正在找回田间记录…'}: {text?: string}) {return <div className="loading" role="status"><div className="loading-skeleton"><i aria-hidden="true"/><i aria-hidden="true"/><i aria-hidden="true"/><span>{text}</span></div></div>}
export function ErrorNote({message, retry}: {message: string; retry?: () => void}) {return message ? <div className="error-note" role="alert"><span>{message}</span>{retry && <button type="button" onClick={retry}>重试</button>}</div> : null}
export function Empty({title, text, action}: {title: string; text: string; action?: ReactNode}) {return <div className="empty-state"><IpIcon name="profile"/><h3>{title}</h3><p>{text}</p>{action}</div>}
export const statusText = (status: string) => ({healthy: '健康', attention: '需关注', awaiting_model: '等待模型', failed: '未完成', queued: '排队中', processing: '分析中'}[status] || status)
export function Badge({status}: {status: string}) {return <span className={`badge ${status}`}>{status === 'healthy' && <Check size={11}/>} {statusText(status)}</span>}
export function SecureImage({url, alt, className = ''}: {url: string; alt: string; className?: string}) {
  const [source, setSource] = useState(''); const [failed, setFailed] = useState(false)
  useEffect(() => {
    let alive = true; let objectUrl = ''; const controller = new AbortController()
    setSource(''); setFailed(false)
    const resolved = new URL(mediaUrl(url), window.location.origin)
    const service = new URL(getServiceBase() || window.location.origin)
    const token = getToken()
    fetch(resolved, {headers: token && resolved.origin === service.origin ? {Authorization: `Bearer ${token}`} : undefined, cache: 'no-store', signal: controller.signal})
      .then(response => {if (!response.ok) throw new Error(); return response.blob()})
      .then(blob => {objectUrl = URL.createObjectURL(blob); if (alive) setSource(objectUrl); else URL.revokeObjectURL(objectUrl)})
      .catch(() => {if (alive) setFailed(true)})
    return () => {alive = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl)}
  }, [url])
  return source ? <img src={source} alt={alt} className={className}/> : <span className={`image-placeholder ${className}`} aria-label={failed ? `${alt}暂不可用` : `正在加载${alt}`}>{failed ? <Leaf size={23}/> : <LoaderCircle className="spin" size={20}/>}</span>
}
export function Sheet({title, children, onClose, dismissible = true}: {title: string; children: ReactNode; onClose: () => void; dismissible?: boolean}) {
  const host = useRef<HTMLDivElement>(null); const close = useRef(onClose); close.current = onClose
  const [closing, setClosing] = useState(false); const closeTimer = useRef<number | undefined>(undefined)
  function requestClose() {if (!dismissible || closeTimer.current != null) return; if (motionReduced()) {close.current(); return}; setClosing(true); closeTimer.current = window.setTimeout(() => close.current(), 250)}
  const request = useRef(requestClose); request.current = requestClose
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null; const unlock = lockBodyScroll()
    host.current?.querySelector<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled)')?.focus()
    const keydown = (event: KeyboardEvent) => {
      const dialogs = document.querySelectorAll('[role="dialog"]')
      if (dialogs[dialogs.length - 1] !== host.current) return
      if (event.key === 'Escape') {event.preventDefault(); request.current()}
      if (event.key !== 'Tab') return
      const list = [...host.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]') ?? []].filter(element => element.offsetParent !== null)
      const first = list[0], last = list[list.length - 1]
      if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus()}
      else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus()}
    }
    document.addEventListener('keydown', keydown)
    return () => {window.clearTimeout(closeTimer.current); unlock(); document.removeEventListener('keydown', keydown); if (previous?.isConnected) previous.focus()}
  }, [])
  return createPortal(<div className={`sheet-overlay ${closing ? 'is-closing' : ''}`} onMouseDown={event => {if (event.target === event.currentTarget) requestClose()}}><div className="sheet" ref={host} role="dialog" aria-modal="true" aria-label={title}><div className="sheet-grip"/><header className="sheet-heading"><h2>{title}</h2><button className="icon-button" aria-label="关闭详情" disabled={!dismissible} onClick={requestClose}><X size={20}/></button></header><div className="sheet-content">{children}</div></div></div>, document.body)
}
export function DetectionResult({record, onAsk, transient = false}: {record: Detection; onAsk?: (record: Detection) => void; transient?: boolean}) {
  const targetDetection=record.prediction_model?.task==='detect'
  const sampleOnly=record.status==='awaiting_model'
  return <div className="detection-result">
    <div className="result-top"><div><span className="eyebrow">{sampleOnly?'采集记录':'叶片观察报告'}</span><h2>{record.crop}<small>{sampleOnly?'照片与备注':'本次观察'}</small></h2></div><Art src={cropThemes[record.crop]?`/images/crops/${cropThemes[record.crop].id}-still.webp`:'/images/xiaohe.png'} alt={`小禾手持${record.crop}`} className="result-mascot"/><Badge status={record.status}/></div>
    {record.is_demo&&<p className="info-note">这是一份示例记录，用于说明页面，不代表实际检测结果。</p>}
    {record.image_url && <SecureImage url={record.image_url} alt={`${record.crop}检测照片`} className="result-photo"/>}
    <div className="diagnosis"><span>{sampleOnly?'样本状态':'病害 / 健康状态'}</span><h3>{sampleOnly?'照片与采样备注已保存':record.result || '尚未生成识别结果'}</h3>{sampleOnly?<p className="form-hint">本条为采集记录，尚未生成病害或健康判断。</p>:<div><span>{targetDetection?'检测目标置信度':'分类置信度'}</span><strong title={`模型原始${targetDetection?'目标分数':'概率'} ${record.confidence ?? '未提供'}`}>{confidence(record.confidence)}</strong></div>}</div>
    {!!record.candidates?.length && <section className="candidate-section"><h3>{targetDetection?'类别目标分数':'模型候选'}<span>{targetDetection?'最高目标置信度':'原始分类概率'}</span></h3>{record.candidates.map((candidate, index) => <div className="candidate" key={candidate.key}><div><span><i>{index + 1}</i>{candidate.label}</span><strong>{confidence(candidate.confidence)}</strong></div><div className="candidate-bar"><i style={{'--candidate-score': Math.max(0, Math.min(1, candidate.confidence))} as CSSProperties}/></div></div>)}<p>{targetDetection?'同类别取最高目标分数，非概率分布，不代表患病概率；各类分数不要求合计为 100%。':'候选是单标签模型的不同判断，不表示同时患有多种病；置信度不等于田间准确率。'}</p></section>}
    <ModelVerification verification={record.prediction_model?.verification}/>
    <div className="report-meta"><span>地块<strong>{record.plot_name || '未关联地块'}</strong></span><span>记录时间<strong>{new Date(record.created_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</strong></span>{record.note && <span>采样备注<strong>{record.note}</strong></span>}</div>
    <div className="advice-card"><Art src="/images/xiaohe.png" alt="小禾农业助手"/><div><h3>和小禾继续聊聊</h3><p>{transient ? '先保存当前画面，再和小禾讨论这次观察。' : sampleOnly?'让小禾结合照片与采样信息，帮你梳理下一步该观察什么。':'结合照片与识别结果，了解异常线索和后续观察建议。'}</p>{onAsk && !transient && <button className="text-button" onClick={() => onAsk(record)}>讨论这份观察<MessageCircle size={14}/></button>}</div></div>
    {targetDetection&&!!record.boxes?.length&&<p className="fine-print">已检测到 {record.boxes.length} 个目标框；目标框不表示精确病斑边界或面积。</p>}{!sampleOnly&&<p className="fine-print"><ShieldCheck size={13}/>识别结果仅作辅助，实际病虫害需结合现场情况确认。</p>}
  </div>
}
export function LinkRow({icon, title, description, onClick,disabled=false}: {icon: ReactNode; title: string; description?: string; onClick: () => void;disabled?:boolean}) {return <button className="link-row" onClick={onClick} disabled={disabled}><span className="row-icon">{icon}</span><span><strong>{title}</strong>{description && <small>{description}</small>}</span><ChevronRight size={18} aria-hidden="true"/></button>}
