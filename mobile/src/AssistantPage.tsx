import {useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowUp, ChevronDown, History, LoaderCircle, Plus, Sprout} from 'lucide-react'
import {api, getServiceBase} from './api'
import {Art, Badge, Empty, ErrorNote, Sheet} from './components'
import {confidence} from './hooks'
import type {ChatDetail, ChatMessage, Conversation, Detection, User} from './types'
import {useClientConfig} from './ClientConfig'
import {ModelVerification} from './ModelVerification'

const analyses = new Map<string, Promise<ChatDetail>>()
function analyzeRecord(record: Detection, user: User) {
  const key = `${getServiceBase()}:${user.username}:${record.id}`
  let promise = analyses.get(key)
  if (!promise) {promise = api<ChatDetail>(`/assistant/detections/${record.id}/analysis`,{method:'POST'},130000).finally(()=>analyses.delete(key));analyses.set(key,promise)}
  return promise
}
export default function AssistantPage({user,record,onHandled,onMinimize,onBusyChange,onReply,visible=true}:{user:User;record:Detection|null;onHandled:()=>void;onMinimize?:()=>void;onBusyChange?:(busy:boolean)=>void;onReply?:()=>void;visible?:boolean}) {
  const {config}=useClientConfig();const enabled=config.features.assistant
  const [chats,setChats]=useState<Conversation[]>([]);const [active,setActive]=useState<Conversation|null>(null);const [messages,setMessages]=useState<ChatMessage[]>([])
  const [draft,setDraft]=useState('');const [busy,setBusy]=useState(false);const [loading,setLoading]=useState(true);const [history,setHistory]=useState(false);const [error,setError]=useState('')
  const [detection,setDetection]=useState<Detection|null>(record);const [failed,setFailed]=useState<Detection|null>(null)
  const log=useRef<HTMLDivElement>(null);const input=useRef<HTMLTextAreaElement>(null);const alive=useRef(true);const request=useRef<AbortController|null>(null)
  const interactionVersion=useRef(0);const replyRef=useRef(onReply);replyRef.current=onReply
  useEffect(()=>{onBusyChange?.(busy)},[busy,onBusyChange])
  useEffect(()=>{if(!visible)setHistory(false)},[visible])
  function update(chat:Conversation) {setActive(chat);setChats(old=>[chat,...old.filter(item=>item.id!==chat.id)].slice(0,100))}
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;request.current?.abort()}},[])
  useEffect(()=>{
    let disposed=false;const version=interactionVersion.current
    api<Conversation[]>('/assistant/conversations').then(async items=>{if(disposed)return;setChats(old=>[...old,...items.filter(item=>!old.some(previous=>previous.id===item.id))]);if(!record&&items[0]&&interactionVersion.current===version){const detail=await api<ChatDetail>(`/assistant/conversations/${items[0].id}`);if(!disposed&&interactionVersion.current===version){setActive(detail.conversation);setMessages(detail.messages)}}}).catch(e=>{if(!disposed&&interactionVersion.current===version)setError(e.message)}).finally(()=>{if(!disposed)setLoading(false)})
    return()=>{disposed=true}
    // Session changes remount this screen; an incoming detection has its own path.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[user.username])
  useEffect(()=>{
    if(!record)return;const version=++interactionVersion.current;request.current?.abort();setLoading(false);if(!enabled){setBusy(false);setError('小禾新问答已暂停，历史对话仍可阅读。');onHandled();return}let disposed=false;setDetection(record);setBusy(true);setError('');setFailed(null);setMessages([]);setActive(null)
    analyzeRecord(record,user).then(value=>{if(!disposed&&interactionVersion.current===version){setMessages(value.messages);update(value.conversation);setBusy(false);replyRef.current?.();onHandled()}}).catch(e=>{if(!disposed&&interactionVersion.current===version){setError(e.message);setFailed(record);setBusy(false);onHandled()}})
    return()=>{disposed=true}
    // The parent clears its request after completion; this effect follows the ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[record?.id,user.username,enabled])
  useEffect(()=>{if(!visible)return;const frame=requestAnimationFrame(()=>{if(log.current)log.current.scrollTop=log.current.scrollHeight});return()=>cancelAnimationFrame(frame)},[messages,busy,detection,visible])
  async function select(chat:Conversation) {if(busy||loading)return;const version=++interactionVersion.current;setLoading(true);setError('');try{const value=await api<ChatDetail>(`/assistant/conversations/${chat.id}`);if(alive.current&&interactionVersion.current===version){setActive(value.conversation);setMessages(value.messages);setDraft('');setDetection(null);setFailed(null);setHistory(false)}}catch(e){if(alive.current&&interactionVersion.current===version)setError((e as Error).message)}finally{if(alive.current&&interactionVersion.current===version)setLoading(false)}}
  function fresh(){if(busy||!enabled)return;interactionVersion.current++;setActive(null);setMessages([]);setDraft('');setDetection(null);setFailed(null);setError('');setHistory(false);input.current?.focus()}
  async function retry(){if(!failed||busy||!enabled)return;const version=++interactionVersion.current;setBusy(true);setError('');try{const value=await analyzeRecord(failed,user);if(alive.current&&interactionVersion.current===version){setMessages(value.messages);update(value.conversation);setFailed(null);replyRef.current?.()}}catch(e){if(alive.current&&interactionVersion.current===version)setError((e as Error).message)}finally{if(alive.current&&interactionVersion.current===version)setBusy(false)}}
  async function send(event:FormEvent) {
    event.preventDefault();const question=draft.trim();if(question.length<2||busy||loading||!enabled||(detection&&!active))return
    const version=++interactionVersion.current;setBusy(true);setError('');const controller=new AbortController();request.current=controller
    try {let conversation=active;if(!conversation){conversation=await api<Conversation>('/assistant/conversations',{method:'POST',signal:controller.signal});if(!alive.current||interactionVersion.current!==version)return;update(conversation)}const value=await api<ChatDetail>(`/assistant/conversations/${conversation.id}/messages`,{method:'POST',body:JSON.stringify({question}),signal:controller.signal},130000);if(alive.current&&interactionVersion.current===version){setMessages(old=>[...old,...value.messages]);update(value.conversation);setDraft('');replyRef.current?.()}}catch(e){if(alive.current&&interactionVersion.current===version)setError((e as Error).message)}finally{if(alive.current&&interactionVersion.current===version)setBusy(false);if(request.current===controller)request.current=null}
  }
  return <div className="assistant-page"><header className="chat-heading"><div className="chat-avatar"><Art src="/images/xiaohe.png" alt="小禾"/></div><div><h1>小禾<span>你的田间好帮手</span></h1><p><i/>{busy?'正在认真整理…':'每一份田间发现，都可以聊聊'}</p></div><button className="icon-button" aria-label="查看私人历史对话" onClick={()=>setHistory(true)}><History size={21}/></button><button className="icon-button" aria-label="新建对话" onClick={fresh} disabled={busy||loading||!enabled}><Plus size={23}/></button>{onMinimize&&<button className="icon-button" aria-label="收起小禾" onClick={onMinimize}><ChevronDown size={23}/></button>}</header>
    {!enabled&&<div className="info-note chat-disabled">小禾新问答已由管理员暂停，历史对话仍可阅读。</div>}<div className="chat-log" ref={log} role="log" aria-live="polite" aria-label="与小禾的私人对话">
      {detection&&<div className="chat-detection"><div><strong>这一次叶片观察</strong><Badge status={detection.status}/></div><h3>{detection.crop} · {detection.result||'等待模型接入'}</h3><p>{detection.prediction_model?.task==='detect'?'检测目标置信度':'分类置信度'} {confidence(detection.confidence)}</p><ModelVerification verification={detection.prediction_model?.verification} compact/></div>}
      {loading&&!messages.length&&!detection?<div className="loading"><LoaderCircle className="spin" size={22}/>正在找回你的田间笔记…</div>:!messages.length&&!busy&&!detection&&<div className="chat-welcome"><Art src="/images/xiaohe.png" alt="小禾愿意听你的田间发现"/><span className="eyebrow">HELLO, FIELD FRIEND</span><h2>你好，我是小禾。</h2><p>叶片有了新变化，或是想聊聊种植？<br/>把你的问题告诉我吧。</p>{['怎样拍清楚叶片上的病斑？','巡田时应该记录哪些信息？'].map(text=><button key={text} onClick={()=>{setDraft(text);input.current?.focus()}}>{text}</button>)}</div>}
      {messages.filter((item,index)=>!(detection&&index===0&&item.role==='user')).map(item=><article key={item.id} className={`chat-bubble ${item.role}`}><span>{item.role==='assistant'?<><Sprout size={13}/>小禾</>:'我'}<time>{new Date(item.created_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</time></span><p>{item.content}</p></article>)}
      {busy&&<div className="chat-thinking" role="status"><Sprout size={16}/>{detection?'正在整理照片线索与复检建议':'小禾正在思考'}<i/><i/><i/></div>}
    </div><div className="chat-bottom"><ErrorNote message={error}/>{failed&&<button className="text-button" disabled={busy||!enabled} onClick={retry}>重试图片解读</button>}<form className="chat-composer" onSubmit={send}><textarea ref={input} aria-label="发送给小禾的问题" value={draft} onChange={event=>setDraft(event.target.value)} placeholder={detection&&!active?'先完成图片解读，或新建对话':'和小禾聊聊你的田间发现…'} rows={2} maxLength={2000} disabled={busy||loading||!enabled||!!(detection&&!active)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();event.currentTarget.form?.requestSubmit()}}}/><button aria-label="发送消息" disabled={draft.trim().length<2||busy||loading||!enabled||!!(detection&&!active)}>{busy?<LoaderCircle className="spin" size={19}/>:<ArrowUp size={22}/>}</button></form><p>AI 回答仅供参考 · 图片不能替代现场确认</p></div>
    {history&&visible&&<Sheet title="我的田间对话" onClose={()=>setHistory(false)}><p className="fine-print">仅当前账户可读取 · 最近 100 段对话</p><div className="chat-history">{chats.map(chat=><button key={chat.id} disabled={busy||loading} className={active?.id===chat.id?'active':''} onClick={()=>select(chat)}><History size={17}/><span><strong>{chat.title}</strong><small>{new Date(chat.updated_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</small></span></button>)}</div>{!chats.length&&<Empty title="你的笔记从这里开始" text="和小禾聊聊，之后可以回来继续这段对话。"/>}</Sheet>}
  </div>
}
