import {useEffect, useLayoutEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowDown, ArrowLeft, ArrowUp, CircleAlert, FileImage, GripHorizontal, History, LoaderCircle, Maximize2, Minimize2, MessageCircle, Minus, Plus, RotateCcw, Shrink, Sprout, X} from 'lucide-react'
import {api,getToken} from './api'
import {useClientConfiguration} from './ClientConfig'
import type {Detection, User} from './types'
import {Badge} from './components'
import {useFloatingPosition, useLauncherPosition} from './useFloatingPosition'
import {confidenceText} from './PredictionScores'
import ModelVerification from './ModelVerification'
import {Xiaohe, type XiaoheState} from './Xiaohe'
import AssistantMessageBody from './AssistantMessageBody'
import './assistant.css'

interface Conversation {id: string; title: string; updated_at: string}
interface Message {id: number; role: 'user' | 'assistant'; content: string; created_at: string}
interface Detail {conversation: Conversation; messages: Message[]}

export default function FloatingAssistant({user, detectionRequests, onDetectionHandled,adviceRequest=null,onAdviceHandled}: {
  user: User | null; detectionRequests: Detection[]; onDetectionHandled: (id: string) => void;adviceRequest?:Detection|null;onAdviceHandled?:()=>void
}) {
  const {features} = useClientConfiguration()
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
  const [showLatest, setShowLatest] = useState(false)
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
  const analysisCache=useRef(new Map<string,{record:Detection;detail:Detail|null;error:string}>())
  const analyzingRecord=useRef<string|null>(null)
  const floating = useFloatingPosition(open, history && wide ? 248 : 0)
  const launcher = useRef<HTMLButtonElement>(null)
  const launcherPosition = useLauncherPosition(launcher, !open)
  const input = useRef<HTMLTextAreaElement>(null)
  const log = useRef<HTMLDivElement>(null)
  const followLatest = useRef(true)
  const readingPosition = useRef(0)
  const scrollMode = useRef<'start'|'end'|null>('end')
  const logWasOpen = useRef(false)
  const alive = useRef(true)
  const mountToken=useRef(getToken())
  const currentSession=()=>alive.current&&getToken()===mountToken.current
  const openRef = useRef(open)
  openRef.current = open

  useEffect(() => {
    if(!currentSession())return
    if (!features.assistant) {
      detectionRequests.forEach(record => onDetectionHandled(record.id))
      return
    }
    if (detectionRequests.length) {setOpen(false); setHistory(false)}
    const next = detectionRequests[0]
    if (!next || !user || loading || busy || handled.current.has(next.id)) return
    handled.current.add(next.id)
    onDetectionHandled(next.id)
    void analyzeDetection(next)
    // Requests are consumed once; pending work waits for the current response.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detectionRequests, user, loading, busy, onDetectionHandled, features.assistant])

  useEffect(()=>{
    if(!adviceRequest||!user||!currentSession()||loading)return
    if(!features.assistant){onAdviceHandled?.();return}
    let cached=analysisCache.current.get(adviceRequest.id)
    if(!cached){
      if(busy||analyzingRecord.current)return
      handled.current.add(adviceRequest.id);onDetectionHandled(adviceRequest.id)
      void analyzeDetection(adviceRequest)
      cached=analysisCache.current.get(adviceRequest.id)
    }
    // Existing queued/cached analyses are reused. If the feature was disabled
    // when saved, this explicit request starts its first analysis only once.
    if(!cached||(analyzingRecord.current&&analyzingRecord.current!==adviceRequest.id)||(busy&&!analyzingRecord.current))return
    setOpen(true);setHistory(false);scrollMode.current='start';setDetection(cached.record)
    if(cached.detail){setMessages(cached.detail.messages);setActive(cached.detail.conversation);setError('');setFailedDetection(null)}
    else if(cached.error){setMessages([]);setActive(null);setError(cached.error);setFailedDetection(cached.record)}
    onAdviceHandled?.()
  },[adviceRequest,user,features.assistant,loading,busy,detection?.id,onAdviceHandled,onDetectionHandled])

  useEffect(() => {
    alive.current = true
    let disposed = false
    if (user&&currentSession()) {
      api<Conversation[]>('/assistant/conversations').then(async items => {
        if (disposed||!currentSession()) return
        setChats(items)
        if (items[0]) {
          const detail = await api<Detail>(`/assistant/conversations/${items[0].id}`)
          if (!disposed&&currentSession()) {setActive(detail.conversation); setMessages(detail.messages)}
        }
      }).catch(e => {if (!disposed&&currentSession()) setError(e.message)}).finally(() => {if (!disposed&&currentSession()) setLoading(false)})
    }
    return () => {disposed = true; alive.current = false;analysisCache.current.clear();handled.current.clear()}
  }, [user])
  useEffect(() => {
    const resize = () => setWide(window.innerWidth >= 600)
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
  useEffect(() => {
    if (currentSession()&&open && !history && !busy && !loading) {input.current?.focus({preventScroll:true}); setUnread(false)}
    // Toggling history must preserve the chat's focus and reading position.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, busy, loading])
  useEffect(() => {
    if (!currentSession()||!open || !history) return
    const panel = historyPanel.current
    const target = panel?.querySelector<HTMLButtonElement>('button[aria-current="true"]:not(:disabled)')
      ?? panel?.querySelector<HTMLButtonElement>('.assistant-history button:not(:disabled)')
      ?? panel?.querySelector<HTMLButtonElement>('button')
    target?.focus({preventScroll: true})
  }, [open, history])
  useLayoutEffect(() => {
    const reopened = open && !logWasOpen.current
    logWasOpen.current = open
    const element = log.current
    if (!open || !element) return
    if (scrollMode.current) {
      element.scrollTop = scrollMode.current === 'start' ? 0 : element.scrollHeight
      scrollMode.current = null
    } else if (followLatest.current) element.scrollTop = element.scrollHeight
    else if (reopened) element.scrollTop = readingPosition.current
    readingPosition.current = element.scrollTop
    followLatest.current = element.scrollHeight - element.clientHeight - element.scrollTop < 64
    setShowLatest(!followLatest.current)
  }, [messages, busy, open, detection])
  useLayoutEffect(() => {
    const element=input.current
    if(!element)return
    element.style.height='0px'
    element.style.height=`${Math.min(104,Math.max(44,element.scrollHeight))}px`
  },[draft,open])

  function scrollToLatest() {
    const element=log.current
    if(element){element.scrollTop=element.scrollHeight;readingPosition.current=element.scrollTop}
    followLatest.current=true;setShowLatest(false)
  }

  function closeHistory() {setHistory(false); requestAnimationFrame(() => {if(currentSession())historyButton.current?.focus({preventScroll: true})})}
  function close() {setOpen(false); setHistory(false); requestAnimationFrame(() => {if(currentSession())launcher.current?.focus()})}
  function fresh() {scrollMode.current='end';setShowLatest(false);setActive(null); setMessages([]); setDraft(''); setError(''); setHistory(false); setDetection(null); setFailedDetection(null)}
  function updateChat(chat: Conversation) {
    setActive(chat); setChats(old => [chat, ...old.filter(item => item.id !== chat.id)].slice(0, 100))
  }
  function rememberConversation(detail:Detail){
    if(!currentSession())return
    for(const [id,cached] of analysisCache.current)if(cached.detail?.conversation.id===detail.conversation.id)analysisCache.current.set(id,{...cached,detail,error:''})
  }
  async function selectChat(chat: Conversation) {
    if(!currentSession())return
    setLoading(true); setError('')
    try {
      const detail = await api<Detail>(`/assistant/conversations/${chat.id}`)
      if (currentSession()) {rememberConversation(detail);scrollMode.current='end';setActive(detail.conversation); setMessages(detail.messages); setDraft(''); setHistory(false); setDetection(null); setFailedDetection(null)}
    } catch(e) {if (currentSession()) setError((e as Error).message)}
    finally {if (currentSession()) setLoading(false)}
  }
  async function analyzeDetection(record: Detection) {
    if (!currentSession()||!features.assistant||analyzingRecord.current) return
    analyzingRecord.current=record.id
    analysisCache.current.set(record.id,{record,detail:null,error:''})
    scrollMode.current='start'
    setHistory(false);setDetection(record);setFailedDetection(null)
    setActive(null); setMessages([]); setError(''); setBusy(true); setAnalyzing(true)
    try {
      const result = await api<Detail>(`/assistant/detections/${record.id}/analysis`, {
        method: 'POST', signal: AbortSignal.timeout(130000),
      })
      if (currentSession()) {
        analysisCache.current.set(record.id,{record,detail:result,error:''})
        scrollMode.current='start'
        setMessages(result.messages); updateChat(result.conversation)
        if (!openRef.current) setUnread(true)
      }
    } catch(e) {
      if (currentSession()) {const message=`检测结果已保存，图片解读暂未完成。${(e as Error).message}`;analysisCache.current.set(record.id,{record,detail:null,error:message});setError(message);setFailedDetection(record)}
    } finally {if(analyzingRecord.current===record.id)analyzingRecord.current=null;if (currentSession()) {setBusy(false); setAnalyzing(false)}}
  }
  async function send(event: FormEvent) {
    event.preventDefault()
    const question = draft.trim()
    if (!currentSession()||!features.assistant || busy || loading || question.length < 2 || !user || (detection && !active)) return
    scrollMode.current='end';setBusy(true); setError('')
    try {
      let chat = active
      if (!chat) {
        chat = await api<Conversation>('/assistant/conversations', {method: 'POST'})
        if (!currentSession()) return
        updateChat(chat)
      }
      const result = await api<Detail>(`/assistant/conversations/${chat.id}/messages`, {
        method: 'POST', body: JSON.stringify({question}), signal: AbortSignal.timeout(130000),
      })
      if (currentSession()) {
        const nextMessages=[...messages,...result.messages]
        rememberConversation({conversation:result.conversation,messages:nextMessages})
        setMessages(nextMessages);updateChat(result.conversation);setDraft('')
        if (!openRef.current) setUnread(true)
      }
    } catch(e) {if (currentSession()) setError((e as Error).message)}
    finally {if (currentSession()) setBusy(false)}
  }
  if(!currentSession())return null
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
          <button onClick={fresh} disabled={!features.assistant || busy || loading} aria-label="新建对话"><Plus size={15}/>新对话</button>
        </div>
        <div className="assistant-conversation">
        <div className="assistant-log" ref={log} role="log" aria-label="与小禾的对话" aria-live="polite" aria-relevant="additions" aria-busy={loading||busy} onScroll={event=>{
          const element=event.currentTarget
          readingPosition.current=element.scrollTop
          followLatest.current=element.scrollHeight-element.clientHeight-element.scrollTop<64
          setShowLatest(!followLatest.current)
        }}>
          {detection && <section className="assistant-detection-card" aria-label="本次检测上下文">
            <div className="assistant-context-heading"><strong><Sprout size={13}/>本次叶片观察</strong><Badge status={detection.status}/></div>
            <h3>{detection.crop}<span>{detection.result || '尚无模型结论'}</span></h3>
            <div className="assistant-context-metrics"><span>{detection.prediction_model?.task === 'detect' || detection.boxes?.length ? '检测目标置信度' : '分类置信度'}<strong>{confidenceText(detection.confidence)}</strong></span>{!!detection.boxes?.length&&<span>识别目标<strong>{detection.boxes.length}<small>个</small></strong></span>}</div>
            <ModelVerification verification={detection.prediction_model?.verification} compact/>
            <details className="assistant-context-details"><summary><FileImage size={12}/><span>{detection.name}</span><span className="assistant-context-more">样本信息</span></summary><p>采样时间：{new Date(detection.created_at).toLocaleString('zh-CN')}</p>{detection.note&&<p>备注：{detection.note}</p>}</details>
            <small className="assistant-context-note">结合照片与检测结果辅助分析，仍需现场观察确认。</small>
          </section>}
          {loading ? <div className="assistant-loading" role="status"><LoaderCircle size={22} className="spin"/><div><strong>正在找回你的田间笔记</strong><span>准备好后，就能接着聊。</span></div></div> : !messages.length && !busy && !detection && <div className="assistant-welcome">
            <Xiaohe state={greeting ? 'wave' : 'idle'}/><span>每一次观察，都值得被记住</span><h3>你好，我是小禾</h3><p>叶片有了新变化，或是想聊聊种植？<br/>告诉我作物、环境和最近的变化，一起理清线索。</p>
            {['巡田时应该记录哪些信息？', '怎样拍清楚叶片上的病斑？'].map(text => <button key={text} disabled={busy} onClick={() => {setDraft(text); input.current?.focus()}}>{text}<ArrowUp size={13}/></button>)}
          </div>}
          {messages.filter((message, index) => !(detection && index === 0 && message.role === 'user')).map(message => <article key={message.id} className={`chat-message ${message.role}`}>
            <span className="chat-speaker">{message.role === 'assistant' ? <><span className="chat-avatar" aria-hidden="true"><Sprout size={13}/></span><strong>小禾</strong><span className="chat-role">田间好帮手</span></> : <strong>我的提问</strong>}<time dateTime={message.created_at} title={new Date(message.created_at).toLocaleString('zh-CN')}>{new Date(message.created_at).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'})}</time></span>
            {message.role==='assistant'?<AssistantMessageBody content={message.content}/>:<p>{message.content}</p>}
          </article>)}
          {busy && <>{!analyzing && <article className="chat-message user pending"><span className="chat-speaker"><strong>我的提问</strong><span className="chat-delivery">等待回复</span></span><p>{draft.trim()}</p></article>}<div className="assistant-thinking" role="status"><span className="assistant-thinking-icon"><Sprout size={18}/></span><div><strong>{analyzing ? '小禾正在看这片叶子' : '小禾正在整理思路'}<span className="assistant-thinking-dots"><i/><i/><i/></span></strong><p>{analyzing?'结合照片，整理可见线索与复检建议。':'把观察变成更清晰、可执行的建议。'}</p></div></div></>}
        </div>
        {showLatest&&<button type="button" className="assistant-latest" onClick={scrollToLatest}><ArrowDown size={13}/>回到最新</button>}
        </div>
        {error && <div className="assistant-error" role="alert"><CircleAlert size={15}/><div><strong>{failedDetection?'图片解读暂未完成':'这次连接没有完成'}</strong><p>{error}</p>{failedDetection ? <button type="button" disabled={!features.assistant || busy} onClick={() => analyzeDetection(failedDetection)}><RotateCcw size={12}/>重试图片解读</button> : active&&draft.trim().length>=2 ? <button type="button" disabled={!features.assistant||busy||loading} onClick={()=>input.current?.form?.requestSubmit()}><RotateCcw size={12}/>再次发送</button> : <button type="button" onClick={() => window.location.reload()}>重新连接</button>}</div></div>}
        {!features.assistant && <div className="assistant-error" role="status">管理员已暂停小禾新问答，历史对话仍可查看。</div>}
        <form className="assistant-composer" onSubmit={send}>
          <div className="assistant-input-wrap"><textarea ref={input} aria-label="发送给小禾的问题" aria-describedby="xiaohe-composer-hint" placeholder={failedDetection ? '重试图片解读，或新建一个话题…' : busy ? '小禾正在回复，请稍等…' : detection?'还想了解这片叶子的哪些情况？':'写下作物、环境或叶片的新变化…'} value={draft} onChange={event => setDraft(event.target.value)} disabled={!features.assistant || busy || loading || !!(detection && !active)} maxLength={2000} rows={2} onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {event.preventDefault(); event.currentTarget.form?.requestSubmit()}
          }}/><button type="submit" aria-label="发送消息" disabled={!features.assistant || busy || loading || !!(detection && !active) || draft.trim().length < 2}>{busy ? <LoaderCircle size={17} className="spin"/> : <ArrowUp size={19}/>}</button></div>
          <div className="assistant-composer-meta" id="xiaohe-composer-hint"><span>AI 建议仅供参考</span>{draft.length>0?<span className={draft.length>1800?'near-limit':''}>{draft.length} / 2000</span>:<span className="assistant-keyboard-hint">Enter 发送 · Shift + Enter 换行</span>}</div>
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
