import {useCallback,useEffect,useRef,useState,type FormEvent} from 'react'
import {Camera,Leaf,X} from 'lucide-react'
import {api,getServiceBase,getToken} from './api'
import CameraCapture from './CameraCapture'
import {Art,ErrorNote} from './components'
import {navigate,useObjectUrl} from './hooks'
import type {Detection,MediaCapabilities,ModelInfo,Plot} from './types'
import {captureNativePhoto,isNativeAndroid} from './native'
import {useClientConfig} from './ClientConfig'
import {CaptureProgress,FeedbackButton} from './Motion'
import {IpIcon} from './IpIcon'
import {DetectionTaskResult} from './DetectionTasks'
import type {TaskRuntime} from './useDetectionTasks'

const modes=[{id:'image',label:'照片',icon:'detect'},{id:'video',label:'视频',icon:'video'},{id:'camera',label:'实时',icon:'camera'}] as const
interface CaptureDraft {file:File|null;plotId:string;note:string;crop:string;taskKey:string|null;previewError:boolean;videoDuration:number}
const emptyDraft=():CaptureDraft=>({file:null,plotId:'',note:'',crop:'番茄',taskKey:null,previewError:false,videoDuration:0})

export default function DetectPage({mode,model,plots,tasks,onAsk,onRecognized,onOpenTask,visible=true}:{mode:string;model:ModelInfo|null;plots:Plot[];tasks:TaskRuntime;onAsk?:(record:Detection)=>void;onRecognized:(crop:string)=>void;onOpenTask:(key:string)=>void;visible?:boolean}){
  const {config}=useClientConfig(),requestedMode=modes.some(item=>item.id===mode)?mode:'image'
  const [current,setCurrent]=useState(requestedMode),[file,setFile]=useState<File|null>(null),[plotId,setPlotId]=useState(''),[note,setNote]=useState(''),[crop,setCrop]=useState('番茄')
  const [taskKey,setTaskKey]=useState<string|null>(null),[error,setError]=useState(''),[message,setMessage]=useState(''),[previewError,setPreviewError]=useState(false),[videoDuration,setVideoDuration]=useState(0)
  const [cameraActive,setCameraActive]=useState(false)
  const cameraActivity=useCallback((active:boolean)=>setCameraActive(active),[])
  const [capabilities,setCapabilities]=useState<MediaCapabilities|null>(null),[capabilityError,setCapabilityError]=useState(''),[capabilityLoading,setCapabilityLoading]=useState(true),[capabilityRetry,setCapabilityRetry]=useState(0)
  const input=useRef<HTMLInputElement>(null),videoPreview=useRef<HTMLVideoElement>(null),mounted=useRef(true),lastSubmitted=useRef(new WeakSet<File>()),currentMode=useRef(current)
  currentMode.current=current
  const visibleRef=useRef(visible);visibleRef.current=visible
  const drafts=useRef(new Map<string,CaptureDraft>()),draft=useRef<CaptureDraft>(emptyDraft())
  draft.current={file,plotId,note,crop,taskKey,previewError,videoDuration}
  const modelKey=JSON.stringify([model?.status,model?.active?.name,model?.active?.pipeline,model?.active?.components?.map(component=>[component.role,component.onnx_sha256])])
  const ready=model?.status==='ready',preview=useObjectUrl(file),job=tasks.jobs.find(item=>item.key===taskKey)
  const enabled=config.features[current==='image'?'image_detection':current==='video'?'video_detection':'live_detection']
  const videoReady=ready&&config.features.video_detection&&Boolean(capabilities?.video_enabled&&capabilities.model_ready),liveReady=ready&&config.features.live_detection&&Boolean(capabilities?.live_enabled&&capabilities.model_ready)
  const maxImage=Math.min(10,config.limits.image_max_mb),maxVideo=Math.min(capabilities?.video_max_mb??50,config.limits.video_max_mb),maxSeconds=Math.min(capabilities?.video_max_seconds??60,config.limits.video_max_seconds),maxFrames=Math.min(capabilities?.video_max_frames??8,config.limits.video_max_frames)
  const canChoose=enabled&&(current==='image'||videoReady),selectablePlots=ready?plots:plots.filter(plot=>plot.crop===crop)
  const fileSizeError=file&&file.size>(current==='image'?maxImage:maxVideo)*1024*1024?`所选文件超过 ${current==='image'?maxImage:maxVideo} MB 上限，请重新选择。`:''
  const durationError=current==='video'&&videoDuration>maxSeconds?`视频最长 ${maxSeconds} 秒，请截取后上传。`:''
  useEffect(()=>{
    if(requestedMode===current)return
    drafts.current.set(current,draft.current);videoPreview.current?.pause()
    const next=drafts.current.get(requestedMode)??emptyDraft()
    setFile(next.file);setPlotId(next.plotId);setNote(next.note);setCrop(next.crop);setTaskKey(next.taskKey);setPreviewError(next.previewError);setVideoDuration(next.videoDuration);setError('');setMessage('');lastSubmitted.current=new WeakSet<File>()
    if(input.current)input.current.value=''
    setCurrent(requestedMode)
  },[requestedMode,current])
  useEffect(()=>{
    let active=true;const controller=new AbortController(),token=getToken(),base=getServiceBase();setCapabilityLoading(true);setCapabilityError('');setCapabilities(null)
    const valid=()=>active&&token===getToken()&&base===getServiceBase()
    api<MediaCapabilities>('/media/capabilities',{signal:controller.signal}).then(value=>{if(valid())setCapabilities(value)}).catch(reason=>{if(valid())setCapabilityError((reason as Error).message)}).finally(()=>{if(valid())setCapabilityLoading(false)})
    return()=>{active=false;controller.abort()}
  },[modelKey,config.version,capabilityRetry])
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  useEffect(()=>{const pause=()=>{if(!visible||document.hidden)videoPreview.current?.pause()};pause();document.addEventListener('visibilitychange',pause);return()=>document.removeEventListener('visibilitychange',pause)},[visible,file,current])
  useEffect(()=>{if(model?.available_crops.length&&!model.available_crops.includes(crop))setCrop(model.available_crops[0])},[model,crop])
  useEffect(()=>{if(plotId&&(!config.features.plots||!selectablePlots.some(plot=>plot.id===plotId)))setPlotId('')},[plotId,config.features.plots,selectablePlots])
  function choose(next?:File){
    if(!next||!canChoose)return
    if(current==='image'&&!['image/jpeg','image/png','image/webp'].includes(next.type)){setError('请选择 JPG、PNG 或 WebP 图片。');return}
    if(current==='video'&&!next.type.startsWith('video/')&&!/\.(mp4|mov|webm|avi)$/i.test(next.name)){setError('请选择 MP4、MOV、WebM 或 AVI 视频。');return}
    if(next.size>(current==='image'?maxImage:maxVideo)*1024*1024){setError(`文件最大 ${current==='image'?maxImage:maxVideo} MB，请压缩后重新选择。`);return}
    lastSubmitted.current=new WeakSet<File>();setFile(next);setTaskKey(null);setError('');setMessage('');setPreviewError(false);setVideoDuration(0)
  }
  async function nativePhoto(){const token=getToken(),base=getServiceBase();try{const photo=await captureNativePhoto();if(photo&&mounted.current&&visibleRef.current&&currentMode.current==='image'&&getToken()===token&&getServiceBase()===base)choose(photo)}catch(reason){if(mounted.current&&getToken()===token&&getServiceBase()===base)setError((reason as Error).message)}}
  function submit(event:FormEvent){
    event.preventDefault()
    if(!file||lastSubmitted.current.has(file)||!enabled||!model||fileSizeError||durationError||current==='camera'||(current==='video'&&!videoReady))return
    try{
      const key=tasks.enqueue({file,kind:current==='video'?'video':'image',note,plot_id:config.features.plots&&plotId?plotId:undefined,crop:current==='image'&&!ready?crop:undefined})
      lastSubmitted.current.add(file);setTaskKey(key);setFile(null);setError('');setMessage('已加入检测任务，可以继续选择文件或切换页面。')
      draft.current={...draft.current,file:null,taskKey:key};if(input.current)input.current.value=''
    }catch(reason){setError((reason as Error).message)}
  }
  const metadata=<div className="capture-information">{!ready&&current==='image'&&<label className="capture-crop">采集作物<select value={crop} onChange={event=>setCrop(event.target.value)}>{model?.available_crops.map(value=><option key={value}>{value}</option>)}</select><small className="form-hint">当前只保存照片与备注，不生成识别结论。</small></label>}<details className="capture-options"><summary>地块与采样备注<span>选填</span></summary><fieldset disabled={current==='camera'&&cameraActive}><div className="capture-meta"><label>关联地块<select value={plotId} disabled={!config.features.plots} onChange={event=>setPlotId(event.target.value)}><option value="">暂不关联地块</option>{selectablePlots.map(plot=><option key={plot.id} value={plot.id}>{plot.name} · {plot.crop}</option>)}</select><small className="form-hint">{!config.features.plots?'地块关联暂未开放。':'提交时固定本次关联，之后修改不会影响已提交任务。'}</small></label><label className="sample-note">采样备注<input value={note} onChange={event=>setNote(event.target.value)} maxLength={500} placeholder="例如：植株中部叶片，雨后采样"/></label></div></fieldset></details></div>
  const unavailable=current!=='image'&&(!ready||(!capabilityLoading&&!capabilityError&&!(current==='video'?videoReady:liveReady)))
  return <div className="detect-page"><div className="page-intro"><h1>{current==='video'?'沿着时间观察':current==='camera'?'走近叶片看看':'记录一片叶子'}</h1><p>{current==='image'?(ready?'选一张清晰的叶片照片，识别作物并保存观察。':'保存照片与采样备注，当前不会生成病害判断。'):current==='video'?'视频会按时间抽样，分别保存观察结果。':'实时相机离开页面即停止；已提交的观察帧会继续保存。'}</p></div>
    <div className="mode-switch" role="group" aria-label="选择观察方式">{modes.map(item=><button key={item.id} className={current===item.id?'active':''} aria-pressed={current===item.id} disabled={!config.features[item.id==='image'?'image_detection':item.id==='video'?'video_detection':'live_detection']} onClick={()=>navigate(`detect/${item.id}`)}><IpIcon name={item.icon}/>{item.label}</button>)}</div>
    {!enabled&&<div className="info-note" role="status">此观察方式暂未开放，已提交任务仍可在任务页查看状态。</div>}
    {current==='image'&&!ready&&<p className="info-note"><Leaf size={17}/>{model?'当前仅采集样本，不生成病害或健康判断。':'正在读取识别服务状态…'}</p>}
    {current!=='image'&&capabilityLoading&&<p className="capture-message" role="status">正在确认媒体观察是否可用…</p>}
    {current!=='image'&&<ErrorNote message={capabilityError} retry={()=>setCapabilityRetry(value=>value+1)}/>}
    {unavailable&&<div className="capture-unavailable"><p>当前视频或实时观察尚不可用，可改用照片采集。</p><button className="button outline" onClick={()=>navigate('detect/image')}>改用照片</button></div>}
    {current!=='camera'&&<form onSubmit={submit}><CaptureProgress sampleOnly={current==='image'&&!ready} fileReady={!!file} linked={Boolean(plotId&&config.features.plots)} complete={false}/><div className={`upload-card ${file?'has-file':''}`}>
      <input ref={input} type="file" accept={current==='image'?'image/jpeg,image/png,image/webp':'video/mp4,video/quicktime,video/webm,video/x-msvideo,.mp4,.mov,.webm,.avi'} aria-label={current==='image'?'选择叶片图片':'选择作物视频'} className="visually-hidden" disabled={!canChoose} onClick={event=>{event.currentTarget.value=''}} onChange={event=>choose(event.target.files?.[0])}/>
      {file?<>{current==='image'?<img className="selected-media" src={preview||undefined} alt="已选择的叶片照片"/>:<video ref={videoPreview} className="selected-media" src={preview||undefined} controls playsInline preload="metadata" onError={()=>setPreviewError(true)} onLoadedMetadata={event=>{setPreviewError(false);setVideoDuration(Number.isFinite(event.currentTarget.duration)?event.currentTarget.duration:0)}}/>}<button className="remove-media" type="button" aria-label="移除所选文件" onClick={()=>{setFile(null);setError('');lastSubmitted.current=new WeakSet<File>();if(input.current)input.current.value=''}}><X size={17}/></button><div className="selected-file"><span>{file.name}</span><small>{(file.size/1024/1024).toFixed(1)} MB</small></div></>:<><Art src={`/images/feature-${current}.webp`} alt={current==='image'?'小禾准备观察叶片':'小禾准备观察视频'} className="upload-art"/><h2>{current==='image'?'一张照片，开始观察':'把巡田过程，交给小禾'}</h2><p>提交后可继续选择下一份文件，或切换到地块与笔记。</p><button className="button primary" type="button" disabled={!canChoose} onClick={()=>input.current?.click()}><IpIcon name={current==='image'?'detect':'video'}/>{current==='image'?'选择叶片照片':'选择作物视频'}</button><small>{current==='image'?`JPG / PNG / WebP · 最大 ${maxImage} MB`:`最大 ${maxVideo} MB · ${maxSeconds} 秒 · 最多 ${maxFrames} 个时点`}</small></>}
    </div>{file&&<button className="text-button change-media" type="button" disabled={!canChoose} onClick={()=>input.current?.click()}>重新选择文件</button>}{metadata}
    {current==='image'&&isNativeAndroid()&&<button className="button outline full native-photo" type="button" onClick={()=>void nativePhoto()} disabled={!enabled}><Camera size={17}/>直接拍一张叶片</button>}
    {previewError&&current==='video'&&<p className="capture-message">当前设备无法预览此格式，仍可上传分析。</p>}<ErrorNote message={error||durationError||fileSizeError}/>{message&&<p className="capture-message" role="status">{message}</p>}
    <FeedbackButton className="primary full detect-submit" type="submit" disabled={!file||!model||!tasks.available||!canChoose||Boolean(fileSizeError||durationError)}><IpIcon name={current==='video'?'video':'detect'}/>{current==='video'?'提交视频任务':ready?'提交检测任务':'提交采集任务'}</FeedbackButton><p className="tasks-inline-note">上传进度会保留在<button type="button" onClick={()=>navigate('tasks')}>检测任务</button>中，切换页面不会中断。</p></form>}
    {current==='camera'&&<>{metadata}<CameraCapture ready={liveReady} visible={visible} plotId={plotId} note={note} onQueueFrame={(frame,options)=>tasks.enqueue({file:frame,kind:'image',...options})} onTaskQueued={key=>setTaskKey(key)} taskState={key=>tasks.jobs.find(item=>item.key===key)?.status} onActive={cameraActivity} onRecognized={onRecognized} intervalMs={Math.max(capabilities?.frame_min_interval_ms??750,config.limits.frame_interval_ms)}/></>}
    {job&&<DetectionTaskResult key={job.key} job={job} runtime={tasks} visible={visible} onAsk={onAsk} onRecognized={current==='camera'?undefined:onRecognized} onOpen={()=>onOpenTask(job.key)}/>}
    {current==='image'&&<div className="photo-tips"><h3>拍清楚，再记录</h3><p>保留完整叶片，避开强烈反光；一次观察一片叶子。{ready?`当前覆盖 ${model.supported_crops.length} 种作物。`:''}</p></div>}
  </div>
}
