import {useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowLeft, ArrowUp, GripHorizontal, History, LoaderCircle, Maximize2, Minimize2, MessageCircle, Minus, Plus, Shrink, Sprout, X} from 'lucide-react'
import {api} from './api'
import type {Detection, User} from './types'
import {Badge} from './components'
import {useFloatingPosition, useLauncherPosition} from './useFloatingPosition'
import {confidenceText} from './PredictionScores'
import {Xiaohe, type XiaoheState} from './Xiaohe'
import './assistant.css'

interface Conversation {id: string; title: string; updated_at: string}
interface Message {id: number; role: 'user' | 'assistant'; content: string; created_at: string}
interface Detail {conversation: Conversation; messages: Message[]}

export default function FloatingAssistant({user, detectionRequests, onDetectionHandled}: {
  user: User | null; detectionRequests: Detection[]; onDetectionHandled: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [history, setHistory] = useState(false)
  const [wide, setWide] = useState(() => window.innerWidth >= 600)
  const historyButton = useRef<HTMLButtonElement>(null)
  const historyPanel = useRef<HTMLElement>(null)
  const [chats, setChats] = useState<Conversation[]>([])
  const [active, setActive] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(!!user)
  const [busy, setBusy] = useState(false)
  const [unread, setUnread] = useState(false)
  const [detection, setDetection] = useState<Detection | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [failedDetection, setFailedDetection] = useState<Detection | null>(null)
  const [greeting, setGreeting] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [celebrating, setCelebrating] = useState(false)
  const wasBusy = useRef(false)
  useEffect(() => {
    if (!open) return
    setGreeting(true)
    const timer = window.setTimeout(() => setGreeting(false), 2400)
    return () => window.clearTimeout(timer)
  }, [open])
  useEffect(() => {
    if (wasBusy.current && !busy && !error) setCelebrating(true)
    wasBusy.current = busy
    if (busy) setCelebrating(false)
  }, [busy, error])
  useEffect(() => {
    if (!celebrating) return
    const timer = window.setTimeout(() => setCelebrating(false), 4200)
    return () => window.clearTimeout(timer)
  }, [celebrating])
  const petState: XiaoheState = analyzing ? 'scan' : busy || loading ? 'think'
    : error || detection?.status === 'attention' ? 'concern'
    : celebrating ? 'success' : greeting || hovered ? 'wave' : 'idle'
  const handled = useRef(new Set<string>())
  const floating = useFloatingPosition(open, history && wide ? 248 : 0)
  const launcher = useRef<HTMLButtonElement>(null)
  const launcherPosition = useLauncherPosition(launcher, !open)
  const input = useRef<HTMLTextAreaElement>(null)
  const log = useRef<HTMLDivElement>(null)
  const alive = useRef(true)
  const openRef = useRef(open)
  openRef.current = open

  useEffect(() => {
    if (detectionRequests.length) {setOpen(true); setHistory(false)}
    const next = detectionRequests[0]
    if (!next || !user || loading || busy || handled.current.has(next.id)) return
    handled.current.add(next.id)
    onDetectionHandled(next.id)
    void analyzeDetection(next)
    // Requests are consumed once; pending work waits for the current response.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detectionRequests, user, loading, busy, onDetectionHandled])

  useEffect(() => {
    alive.current = true
    let disposed = false
    if (user) {
      api<Conversation[]>('/assistant/conversations').then(async items => {
        if (disposed) return
        setChats(items)
        if (items[0]) {
          const detail = await api<Detail>(`/assistant/conversations/${items[0].id}`)
          if (!disposed) {setActive(detail.conversation); setMessages(detail.messages)}
        }
      }).catch(e => {if (!disposed) setError(e.message)}).finally(() => {if (!disposed) setLoading(false)})
    }
    return () => {disposed = true; alive.current = false}
  }, [user])
  useEffect(() => {
    const resize = () => setWide(window.innerWidth >= 600)
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
  useEffect(() => {
    if (open && !history && !busy && !loading) {input.current?.focus(); setUnread(false)}
    // Toggling history must preserve the chat's focus and reading position.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, busy, loading])
  useEffect(() => {
    if (!open || !history) return
    const panel = historyPanel.current
    const target = panel?.querySelector<HTMLButtonElement>('button[aria-current="true"]:not(:disabled)')
      ?? panel?.querySelector<HTMLButtonElement>('.assistant-history button:not(:disabled)')
      ?? panel?.querySelector<HTMLButtonElement>('button')
    target?.focus({preventScroll: true})
  }, [open, history])
  useEffect(() => {
    if (log.current) log.current.scrollTop = detection && messages.length === 2 && !busy ? 0 : log.current.scrollHeight
  }, [messages, busy, open, detection])

  function closeHistory() {setHistory(false); requestAnimationFrame(() => historyButton.current?.focus({preventScroll: true}))}
  function close() {setOpen(false); setHistory(false); requestAnimationFrame(() => launcher.current?.focus())}
  function fresh() {setActive(null); setMessages([]); setDraft(''); setError(''); setHistory(false); setDetection(null); setFailedDetection(null)}
  function updateChat(chat: Conversation) {
    setActive(chat); setChats(old => [chat, ...old.filter(item => item.id !== chat.id)].slice(0, 100))
  }
  async function selectChat(chat: Conversation) {
    setLoading(true); setError('')
    try {
      const detail = await api<Detail>(`/assistant/conversations/${chat.id}`)
      if (alive.current) {setActive(detail.conversation); setMessages(detail.messages); setDraft(''); setHistory(false); setDetection(null); setFailedDetection(null)}
    } catch(e) {if (alive.current) setError((e as Error).message)}
    finally {if (alive.current) setLoading(false)}
  }
  async function analyzeDetection(record: Detection) {
    setOpen(true); setHistory(false); setDetection(record); setFailedDetection(null)
    setActive(null); setMessages([]); setError(''); setBusy(true); setAnalyzing(true)
    try {
      const result = await api<Detail>(`/assistant/detections/${record.id}/analysis`, {
        method: 'POST', signal: AbortSignal.timeout(130000),
      })
      if (alive.current) {
        setMessages(result.messages); updateChat(result.conversation)
        if (!openRef.current) setUnread(true)
      }
    } catch(e) {
      if (alive.current) {setError(`检测结果已保存，图片解读暂未完成。${(e as Error).message}`); setFailedDetection(record)}
    } finally {if (alive.current) {setBusy(false); setAnalyzing(false)}}
  }
  async function send(event: FormEvent) {
    event.preventDefault()
    const question = draft.trim()
    if (busy || loading || question.length < 2 || !user || (detection && !active)) return
    setBusy(true); setError('')
    try {
      let chat = active
      if (!chat) {
        chat = await api<Conversation>('/assistant/conversations', {method: 'POST'})
        if (!alive.current) return
        updateChat(chat)
      }
      const result = await api<Detail>(`/assistant/conversations/${chat.id}/messages`, {
        method: 'POST', body: JSON.stringify({question}), signal: AbortSignal.timeout(130000),
      })
      if (alive.current) {
        setMessages(old => [...old, ...result.messages]); updateChat(result.conversation); setDraft('')
        if (!openRef.current) setUnread(true)
      }
    } catch(e) {if (alive.current) setError((e as Error).message)}
    finally {if (alive.current) setBusy(false)}
  }
  return <div className="assistant-widget" style={!open ? launcherPosition.style : undefined}>
    {open && <section ref={floating.panel} style={floating.style} id="xiaohe-window" className="assistant-window" role="dialog" aria-label="小禾聊天助手" onKeyDown={event => {
      if (event.key === 'Escape') {event.stopPropagation(); if (history) closeHistory(); else close()}
    }}>
      <header className="assistant-header" {...floating.dragHandlers} tabIndex={0} aria-label="拖动小禾窗口，或用方向键移动" title="拖动标题栏移动窗口；方向键也可移动">
        <span className="assistant-face"><Xiaohe state={petState} crop={detection?.crop}/></span>
        <div><h2>小禾<span>田间好帮手</span></h2><p><i/>{analyzing ? '正在查看叶片与检测结果…' : busy ? '正在认真思考…' : '拖动标题栏，放到顺手的位置'}</p></div>
        <GripHorizontal size={16} className="assistant-drag-grip" aria-hidden="true"/>
        <button className="icon-button" aria-label="缩小窗口" title="缩小窗口" onClick={floating.compact}><Shrink size={16}/></button>
        <button className="icon-button" aria-label={floating.maximized ? '还原窗口' : '放大窗口'} title={floating.maximized ? '还原窗口' : '放大窗口'} onClick={floating.toggleMaximize}>{floating.maximized ? <Minimize2 size={16}/> : <Maximize2 size={16}/>}</button>
        <button className="icon-button" aria-label="收起小禾" title="收起" onClick={close}><Minus size={19}/></button>
      </header>
      {user && history && <aside ref={historyPanel} id="xiaohe-history" className="assistant-history-menu" aria-label="小禾历史对话">
        <div className="assistant-history-heading"><h3><History size={14}/>历史对话</h3><button type="button" className="icon-button" onClick={closeHistory} aria-label="关闭历史对话"><X size={16}/></button></div>
        <p className="assistant-history-caption">你的田间笔记 · 最近 100 段对话</p>
        <div className="assistant-history">
          {chats.map(chat => <button key={chat.id} className={active?.id === chat.id ? 'active' : ''} aria-current={active?.id === chat.id ? 'true' : undefined} onClick={() => selectChat(chat)} disabled={busy || loading}>
            <MessageCircle size={16}/><span><strong>{chat.title}</strong><small>{new Date(chat.updated_at).toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'})}</small></span><ArrowLeft className="history-arrow" size={14}/>
          </button>)}
          {!chats.length && <p className="assistant-history-empty">还没有历史对话，和小禾打个招呼吧。</p>}
        </div>
      </aside>}
      <div className="assistant-main">
      {user ? <>
        <div className="assistant-toolbar">
          <button ref={historyButton} type="button" onClick={() => history ? closeHistory() : setHistory(true)} aria-label={history ? '收起历史对话' : '查看历史对话'} aria-expanded={history} aria-controls="xiaohe-history"><History size={14}/>历史对话</button>
          <span title={active?.title}>{active?.title || '新的田间话题'}</span>
          <button onClick={fresh} disabled={busy || loading} aria-label="新建对话"><Plus size={15}/>新对话</button>
        </div>
        <div className="assistant-log" ref={log} role="log" aria-label="与小禾的对话" aria-live="polite" aria-relevant="additions">
          {detection && <div className="assistant-detection-card">
            <div><strong>刚刚完成的检测</strong><Badge status={detection.status}/></div>
            <h3>{detection.crop} · {detection.result || '尚无模型结论'}</h3>
            <p>{detection.name}</p>
            <span>分类置信度：{confidenceText(detection.confidence)}</span>
            <small>分类与照片解读仅供辅助判断，不能据此排除虫害。</small>
          </div>}
          {loading ? <div className="assistant-loading"><LoaderCircle size={20} className="spin"/>正在找回你的田间笔记…</div> : !messages.length && !busy && !detection && <div className="assistant-welcome">
            <Xiaohe state={greeting ? 'wave' : 'idle'}/><span>每一次观察，都值得被记住</span><h3>你好，我是小禾 🌱</h3><p>叶片有了新变化，或是想聊聊种植？<br/>把你的问题告诉我吧。</p>
            {['巡田时应该记录哪些信息？', '怎样拍清楚叶片上的病斑？'].map(text => <button key={text} disabled={busy} onClick={() => {setDraft(text); input.current?.focus()}}>{text}<ArrowUp size={13}/></button>)}
          </div>}
          {messages.filter((message, index) => !(detection && index === 0 && message.role === 'user')).map(message => <article key={message.id} className={`chat-message ${message.role}`}>
            <span className="chat-speaker">{message.role === 'assistant' ? <><Sprout size={13}/>小禾</> : '我'}<time>{new Date(message.created_at).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'})}</time></span>
            <p>{message.content}</p>
          </article>)}
          {busy && <>{!analyzing && <article className="chat-message user"><span className="chat-speaker">我</span><p>{draft.trim()}</p></article>}<div className="assistant-thinking" role="status"><Sprout size={15}/><span>{analyzing ? '正在整理病虫害线索与复检建议' : '小禾正在思考'}</span><i/><i/><i/></div></>}
        </div>
        {error && <div className="assistant-error" role="alert">{error}{failedDetection ? <button disabled={busy} onClick={() => analyzeDetection(failedDetection)}>重试图片解读</button> : <button onClick={() => window.location.reload()} hidden={!loading && !!active}>重新连接</button>}</div>}
        <form className="assistant-composer" onSubmit={send}>
          <div><textarea ref={input} aria-label="发送给小禾的问题" placeholder={failedDetection ? '请重试图片解读，或新建对话…' : '和小禾聊聊你的田间发现…'} value={draft} onChange={event => setDraft(event.target.value)} disabled={busy || loading || !!(detection && !active)} maxLength={2000} rows={2} onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {event.preventDefault(); event.currentTarget.form?.requestSubmit()}
          }}/><button type="submit" aria-label="发送消息" disabled={busy || loading || !!(detection && !active) || draft.trim().length < 2}>{busy ? <LoaderCircle size={17} className="spin"/> : <ArrowUp size={19}/>}</button></div>
          <p>AI 回答仅供参考 · Enter 发送，Shift + Enter 换行</p>
        </form>
      </> : <div className="assistant-guest"><Xiaohe state="wave"/><h3>你好，田间的新朋友</h3><p>登录后就能和小禾聊天，<br/>你的对话也会自动保存。</p><a className="button primary" href="#login">登录后开始聊天</a></div>}
      </div>
      {!floating.maximized && <button className="assistant-resize" {...floating.resizeHandlers} aria-label="调整窗口大小，方向键可放大或缩小" title="拖动调整大小；方向键也可调整"><span/></button>}
    </section>}
    {!open && <button ref={launcher} className="assistant-launcher" aria-label="打开小禾助手" aria-expanded={false} aria-controls="xiaohe-window"
      title="点击打开助手；拖动或使用方向键移动" {...launcherPosition.handlers} onClick={event => {if (!launcherPosition.consumeClick(event)) setOpen(true)}}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onFocus={() => setHovered(true)} onBlur={() => setHovered(false)}>
      <Xiaohe state={petState} crop={analyzing ? detection?.crop : undefined}/><span>小禾</span>{unread && <i aria-label="有新回复"/>}
    </button>}
  </div>
}
