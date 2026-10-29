import {useEffect, useRef, useState} from 'react'
import {Camera, CircleStop, Pause, Play, Save, ScanLine} from 'lucide-react'
import {api,getServiceBase,getToken} from './api'
import {DetectionResult, ErrorNote} from './components'
import {useObjectUrl} from './hooks'
import type {Detection} from './types'
import {ensureCameraPermission} from './native'
import {useClientConfig} from './ClientConfig'

export default function CameraCapture({ready, plotId, note, onQueueFrame,onTaskQueued,taskState,onActive, onRecognized,intervalMs,visible=true}: {ready: boolean; plotId: string; note: string; onQueueFrame:(file:File,options:{plot_id?:string;note?:string})=>string;onTaskQueued:(key:string)=>void;taskState:(key:string)=>string|undefined;onActive: (active: boolean) => void; onRecognized:(crop:string)=>void;intervalMs:number;visible?:boolean}) {
  const {config}=useClientConfig();const interval=useRef(intervalMs);interval.current=Math.max(750,intervalMs)
  const video = useRef<HTMLVideoElement>(null); const canvas = useRef<HTMLCanvasElement>(null)
  const stream = useRef<MediaStream | null>(null); const timer = useRef<number | undefined>(undefined)
  const request = useRef<AbortController | null>(null); const running = useRef(false); const generation = useRef(0); const inFlight = useRef(false); const mounted = useRef(true)
  const metadata = useRef({plotId,note}); metadata.current = {plotId,note}
  const [active, setActive] = useState(false); const [paused, setPaused] = useState(true); const [starting, setStarting] = useState(false)
  const [inspecting, setInspecting] = useState(false); const [saving, setSaving] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('')
  const [result, setResult] = useState<Detection | null>(null); const [lastFrame, setLastFrame] = useState<Blob | null>(null); const [count, setCount] = useState(0)
  const [savedTask,setSavedTask]=useState<string|null>(null)
  const savedTaskRef=useRef<string|null>(null)
  const scope=useRef({token:getToken(),base:getServiceBase()})
  const currentSession=()=>mounted.current&&scope.current.token===getToken()&&scope.current.base===getServiceBase()
  const retryAllowed=Boolean(savedTask&&['failed','cancelled'].includes(taskState(savedTask)||''))
  const savingRef=useRef(false)
  const activeCallback=useRef(onActive);activeCallback.current=onActive
  const preview = useObjectUrl(lastFrame)
  useEffect(() => {onActive(active || starting || saving)}, [active, starting, saving, onActive])
  useEffect(()=>{if(!ready&&(stream.current||starting)){stop();setMessage('实时检测当前不可用，摄像头已停止。')}},[ready])
  useEffect(()=>{if(!visible&&(stream.current||starting)){stop();setMessage('已离开实时观察，相机已关闭。返回后可重新开启。')}},[visible])
  function stop(update = true) {
    generation.current++; running.current = false; window.clearTimeout(timer.current); request.current?.abort()
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null
    if (video.current) video.current.srcObject = null
    if (update && mounted.current) {setActive(false); setPaused(true); setStarting(false); setInspecting(false)}
  }
  useEffect(() => {
    mounted.current = true
    const visibility = () => {if (document.hidden) {stop(); setMessage('已切至后台，摄像头已停止。回来后可重新开启。')}}
    document.addEventListener('visibilitychange', visibility)
    return () => {mounted.current = false; stop(false);activeCallback.current(false); document.removeEventListener('visibilitychange', visibility)}
    // Camera lifetime follows this screen, never background navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  function pause() {generation.current++; running.current = false; window.clearTimeout(timer.current); request.current?.abort(); setPaused(true); setMessage('已暂停识别，摄像头预览继续。可保存最近一次观察。')}
  function schedule(cycle: number, delay = interval.current) {timer.current = window.setTimeout(() => void inspect(cycle), delay)}
  async function inspect(cycle: number) {
    if (!running.current || generation.current !== cycle || !stream.current || !currentSession() || !visible) return
    if (inFlight.current) {schedule(cycle, 200); return}
    const element = video.current, surface = canvas.current
    if (!element || !surface || element.readyState < 2 || !element.videoWidth) {schedule(cycle, 500); return}
    inFlight.current = true; setInspecting(true)
    const controller = new AbortController(); request.current = controller
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    try {
      const scale = Math.min(1, 1024 / Math.max(element.videoWidth, element.videoHeight))
      surface.width = Math.round(element.videoWidth * scale); surface.height = Math.round(element.videoHeight * scale)
      const context=surface.getContext('2d');if(!context)throw new Error('当前设备无法读取相机画面，请改用照片观察。');context.drawImage(element, 0, 0, surface.width, surface.height)
      const blob = await new Promise<Blob | null>(resolve => surface.toBlob(resolve, 'image/jpeg', .87))
      if (!blob || generation.current !== cycle || !running.current || !currentSession()) return
      const body = new FormData(); body.append('file', blob, 'camera-frame.jpg')
      if (metadata.current.plotId) body.append('plot_id', metadata.current.plotId)
      body.append('note', metadata.current.note)
      const record = await api<Detection>('/media/frame', {method:'POST',body,signal:controller.signal})
      if (generation.current !== cycle || !currentSession()) return
      savedTaskRef.current=null;setResult(record); setLastFrame(blob);setSavedTask(null); setCount(value => value + 1); setError(''); setMessage('识别已更新。请缓慢移动，让单片叶子保持清晰。');onRecognized(record.crop)
    } catch(e) {
      if (generation.current === cycle && currentSession()) {running.current = false; setPaused(true); setError((e as Error).message); setMessage('识别已暂停，可重试或停止摄像头。')}
    } finally {
      window.clearTimeout(timeout); inFlight.current = false
      if (currentSession()) setInspecting(false)
      if (running.current && generation.current === cycle) schedule(cycle)
    }
  }
  function resume() {if (!stream.current || saving || !ready || !visible || !currentSession()) return; const cycle = ++generation.current; running.current = true; setPaused(false); setError(''); setMessage('正在继续观察，上一帧识别完成后再读取下一帧。'); schedule(cycle, 50)}
  async function start() {
    if (starting || active || savingRef.current || !ready || !visible || !currentSession()) return
    if (!navigator.mediaDevices?.getUserMedia) {setError('此环境无法访问相机，请使用 HTTPS、手机应用，或改用图片检测。'); return}
    setStarting(true); setError(''); setMessage('正在请求摄像头权限…'); const cycle = ++generation.current
    try {
      await ensureCameraPermission()
      if (!currentSession() || generation.current !== cycle) return
      const source = await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:960}},audio:false})
      if (!currentSession() || generation.current !== cycle) {source.getTracks().forEach(track => track.stop()); return}
      stream.current = source
      if (!video.current) throw new Error('相机预览尚未就绪，请重试。')
      video.current.srcObject = source; await video.current.play()
      if (!currentSession() || generation.current !== cycle) {stop();return}
      savedTaskRef.current=null;setResult(null);setLastFrame(null);setSavedTask(null);setCount(0);setActive(true); setStarting(false); running.current = true; setPaused(false); setMessage('实时观察已开始，画面会按间隔发送识别。'); schedule(cycle, 350)
    } catch(e) {
      if (currentSession() && generation.current === cycle) {stop(); setError(e instanceof DOMException && e.name === 'NotAllowedError' ? '未获得相机权限。请在系统或浏览器设置中允许相机，再重试。' : (e as Error).message)}
    } finally {if (currentSession() && generation.current === cycle) setStarting(false)}
  }
  function saveFrame() {
    const savedKey=savedTaskRef.current,canRetry=savedKey&&['failed','cancelled'].includes(taskState(savedKey)||'')
    if (!currentSession()||!lastFrame || !paused || inspecting || savingRef.current || (savedKey&&!canRetry) || !config.features.image_detection) return
    savingRef.current=true;setSaving(true); setError('')
    try {const key=onQueueFrame(new File([lastFrame],'巡田相机.jpg',{type:'image/jpeg'}),{plot_id:config.features.plots&&plotId?plotId:undefined,note:note||'来自实时相机的已选观察帧'});savedTaskRef.current=key;setSavedTask(key);onTaskQueued(key);setMessage('这帧观察已加入任务，离开相机页面后仍会继续保存。')}
    catch(e) {if(mounted.current)setError((e as Error).message)} finally {savingRef.current=false;if(mounted.current)setSaving(false)}
  }
  return <div className="camera-capture"><div className={`camera-view ${active ? 'is-active' : ''}`}><video ref={video} autoPlay muted playsInline aria-label="后置相机实时预览"/>{!active && <div className="camera-empty"><Camera size={44}/><h3>让小禾看一眼叶片</h3><p>开启后置相机，单片叶子尽量占满取景区域。</p></div>}{active && <><div className="scan-corners"><i/><i/><i/><i/></div><span className="camera-live"><i className={paused ? 'paused' : ''}/>{paused ? '已暂停识别' : inspecting ? '正在识别一帧' : '实时观察中'}</span><span className="camera-frame-count">已观察 {count} 帧</span></>}<canvas ref={canvas} hidden/></div>
    <ErrorNote message={error}/>{message && <p className="capture-message" role="status">{message}</p>}
    <div className="camera-actions">{!active ? <button className="button primary full" onClick={start} disabled={starting || saving || !ready}>{starting ? '正在开启…' : '开启实时相机'}<Camera size={18}/></button> : <><button className="button primary" onClick={paused ? resume : pause} disabled={saving}>{paused ? <Play size={17}/> : <Pause size={17}/>} {paused ? '继续识别' : '暂停识别'}</button><button className="button outline" onClick={() => {stop(); setMessage('摄像头已关闭。')}} disabled={saving}><CircleStop size={17}/>停止相机</button></>}</div>
    {result && <section className="card camera-result"><div className="section-heading"><h2><ScanLine size={16}/>最近一帧</h2><span>{savedTask?'已提交任务':'尚未保存'}</span></div>{preview && <img className="camera-last-frame" src={preview} alt="最近一次识别的相机画面"/>}<DetectionResult record={result} transient/><button className={`button outline full camera-save-feedback ${savedTask&&!retryAllowed?'is-saved':''}`} onClick={saveFrame} disabled={Boolean(savedTask&&!retryAllowed) || !paused || inspecting || saving || !config.features.image_detection}><Save size={17}/>{saving?'正在加入任务…':retryAllowed?'重新提交这帧观察':savedTask?'这帧已加入任务':'保存这帧观察'}</button>{savedTask?<p className="fine-print" role="status">在检测任务中查看进度、取消或结果。继续识别新画面后，可保存下一次观察。</p>:!config.features.image_detection?<p className="fine-print">管理员已暂停图片保存功能，当前帧仍可查看。</p>:!paused&&<p className="fine-print">暂停识别后，可保存最近一帧。</p>}</section>}
    <p className="fine-print">相机会间隔识别画面，不会自动保存每一帧。暂停后可保存最近一次观察；离开检测页或切至后台会关闭相机。</p>
  </div>
}
