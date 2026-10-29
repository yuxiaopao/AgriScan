import {useEffect, useRef, useState, type ReactNode} from 'react'
import {ArrowUpRight, Check, Leaf, LoaderCircle, MessageCircle, ShieldCheck, X} from 'lucide-react'
import {getServiceBase, getToken, mediaUrl} from './api'
import {confidence} from './hooks'
import type {Detection} from './types'
import {cropThemes} from './cropThemes'

export function Art({src, alt, className = ''}: {src: string; alt: string; className?: string}) {
  return <img src={src} alt={alt} className={className} draggable={false} onError={event => {if (!event.currentTarget.src.endsWith('/images/xiaohe.png')) event.currentTarget.src = '/images/xiaohe.png'}}/>
}
export function Loading({text = '正在找回田间记录…'}: {text?: string}) {return <div className="loading" role="status"><LoaderCircle className="spin" size={22}/><span>{text}</span></div>}
export function ErrorNote({message, retry}: {message: string; retry?: () => void}) {return message ? <div className="error-note" role="alert"><span>{message}</span>{retry && <button type="button" onClick={retry}>重试</button>}</div> : null}
export function Empty({title, text, action}: {title: string; text: string; action?: ReactNode}) {return <div className="empty-state"><Leaf size={31}/><h3>{title}</h3><p>{text}</p>{action}</div>}
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
export function Sheet({title, children, onClose}: {title: string; children: ReactNode; onClose: () => void}) {
  const host = useRef<HTMLDivElement>(null); const close = useRef(onClose); close.current = onClose
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null; const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'; host.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {event.preventDefault(); close.current()}
      if (event.key !== 'Tab') return
      const list = [...host.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]') ?? []].filter(element => element.offsetParent !== null)
      const first = list[0], last = list[list.length - 1]
      if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus()}
      else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus()}
    }
    document.addEventListener('keydown', keydown)
    return () => {document.body.style.overflow = oldOverflow; document.removeEventListener('keydown', keydown); previous?.focus()}
  }, [])
  return <div className="sheet-overlay" onMouseDown={event => {if (event.target === event.currentTarget) onClose()}}><div className="sheet" ref={host} role="dialog" aria-modal="true" aria-label={title}><div className="sheet-grip"/><header className="sheet-heading"><h2>{title}</h2><button className="icon-button" aria-label="关闭详情" onClick={onClose}><X size={20}/></button></header><div className="sheet-content">{children}</div></div></div>
}
export function DetectionResult({record, onAsk, transient = false}: {record: Detection; onAsk?: (record: Detection) => void; transient?: boolean}) {
  const targetDetection=record.prediction_model?.task==='detect'
  return <div className="detection-result">
    <div className="result-top"><div><span className="eyebrow">LEAF OBSERVATION</span><h2>{record.crop}<small>检测室</small></h2></div><Art src={cropThemes[record.crop]?`/images/crops/${cropThemes[record.crop].id}-still.webp`:'/images/xiaohe.png'} alt={`小禾手持${record.crop}`} className="result-mascot"/><Badge status={record.status}/></div>
    {record.image_url && <SecureImage url={record.image_url} alt={`${record.crop}检测照片`} className="result-photo"/>}
    <div className="diagnosis"><span>病害 / 健康状态</span><h3>{record.result || '样本已保存，等待模型接入'}</h3><div><span>{targetDetection?'检测目标置信度':'分类置信度'}</span><strong title={`模型原始${targetDetection?'目标分数':'概率'} ${record.confidence ?? '未提供'}`}>{confidence(record.confidence)}</strong></div></div>
    {!!record.candidates?.length && <section className="candidate-section"><h3>{targetDetection?'类别目标分数':'模型候选'}<span>{targetDetection?'最高目标置信度':'原始分类概率'}</span></h3>{record.candidates.map((candidate, index) => <div className="candidate" key={candidate.key}><div><span><i>{index + 1}</i>{candidate.label}</span><strong>{confidence(candidate.confidence)}</strong></div><div className="candidate-bar"><i style={{width: `${candidate.confidence * 100}%`}}/></div></div>)}<p>{targetDetection?'同类别取最高目标分数，非概率分布，不代表患病概率；各类分数不要求合计为 100%。':'候选是单标签模型的不同判断，不表示同时患有多种病；置信度不等于田间准确率。'}</p></section>}
    <div className="report-meta"><span>地块<strong>{record.plot_name || '未关联地块'}</strong></span><span>记录时间<strong>{new Date(record.created_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</strong></span>{record.note && <span>采样备注<strong>{record.note}</strong></span>}</div>
    <div className="advice-card"><Art src="/images/xiaohe.png" alt="小禾农业助手"/><div><h3>让小禾再看仔细一点</h3><p>{transient ? '实时画面尚未保存。先保存当前帧，再让小禾结合照片给出建议。' : '结合照片与模型结果，了解异常线索、处理步骤与复检建议。'}</p>{onAsk && <button className="text-button" onClick={() => onAsk(record)}>向小禾询问建议<MessageCircle size={14}/></button>}</div></div>
    {targetDetection&&!!record.boxes?.length&&<p className="fine-print">已检测到 {record.boxes.length} 个目标框；目标框不表示精确病斑边界或面积。</p>}<p className="fine-print"><ShieldCheck size={13}/>{targetDetection?'目标识别':'照片分类'}仅作辅助，实际病虫害需结合现场情况确认。</p>
  </div>
}
export function LinkRow({icon, title, description, onClick,disabled=false}: {icon: ReactNode; title: string; description?: string; onClick: () => void;disabled?:boolean}) {return <button className="link-row" onClick={onClick} disabled={disabled}><span className="row-icon">{icon}</span><span><strong>{title}</strong>{description && <small>{description}</small>}</span><ArrowUpRight size={17}/></button>}
