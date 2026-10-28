import {useEffect, useRef, useState, type FormEvent} from 'react'
import {Camera, CheckCircle2, Film, ImagePlus, Leaf, LoaderCircle, Play, ScanLine, Upload, X} from 'lucide-react'
import {api} from './api'
import CameraCapture from './CameraCapture'
import {Art, Badge, DetectionResult, ErrorNote} from './components'
import {formatFrameTime, formatTime, navigate, useObjectUrl} from './hooks'
import type {Detection, MediaCapabilities, ModelInfo, Plot, VideoResult} from './types'
import {captureNativePhoto, isNativeAndroid} from './native'
import {useClientConfig} from './ClientConfig'

const modes = [{id:'image',label:'图片检测',icon:ImagePlus},{id:'video',label:'视频检测',icon:Film},{id:'camera',label:'实时相机',icon:Camera}]
export default function DetectPage({mode, model, plots, onSaved, onAsk, onRecognized}: {mode: string; model: ModelInfo | null; plots: Plot[]; onSaved: (record?: Detection) => void; onAsk?: (record: Detection) => void;onRecognized:(crop:string)=>void}) {
  const {config}=useClientConfig()
  const current = modes.some(item => item.id === mode) ? mode : 'image'
  const [file, setFile] = useState<File | null>(null); const [plotId,setPlotId] = useState(''); const [note,setNote] = useState(''); const [crop,setCrop] = useState('番茄')
  const [busy,setBusy] = useState(false); const [cameraActive,setCameraActive] = useState(false); const [error,setError] = useState(''); const [message,setMessage] = useState('')
  const [result,setResult] = useState<Detection | null>(null); const [videoResult,setVideoResult] = useState<VideoResult | null>(null); const [selectedFrame,setSelectedFrame] = useState(0)
  const [capabilities,setCapabilities]=useState<MediaCapabilities|null>(null);const [capabilityError,setCapabilityError]=useState('');const [durationError,setDurationError]=useState('');const [observedCrop,setObservedCrop]=useState('')
  const [previewError,setPreviewError]=useState(false)
  const [videoDuration,setVideoDuration]=useState(0)
  const input = useRef<HTMLInputElement>(null); const controller = useRef<AbortController | null>(null); const alive = useRef(true)
  const preview = useObjectUrl(file); const ready = model?.status === 'ready'; const locked = busy || cameraActive
  const currentEnabled=config.features[current==='image'?'image_detection':current==='video'?'video_detection':'live_detection']
  const videoReady=ready&&config.features.video_detection&&!!capabilities?.video_enabled&&capabilities.model_ready;const liveReady=ready&&config.features.live_detection&&!!capabilities?.live_enabled&&capabilities.model_ready
  const maxImage=Math.min(10,config.limits.image_max_mb);const maxVideo=Math.min(capabilities?.video_max_mb??50,config.limits.video_max_mb);const maxSeconds=Math.min(capabilities?.video_max_seconds??60,config.limits.video_max_seconds);const maxFrames=Math.min(capabilities?.video_max_frames??8,config.limits.video_max_frames)
  const fileSizeError=file&&file.size>(current==='image'?maxImage:maxVideo)*1024*1024?`所选文件超过当前 ${current==='image'?maxImage:maxVideo} MB 上限，请重新选择。`:''
  useEffect(()=>{let disposed=false;api<MediaCapabilities>('/media/capabilities').then(value=>{if(!disposed)setCapabilities(value)}).catch(e=>{if(!disposed)setCapabilityError(e.message)});return()=>{disposed=true}},[model?.status,config.version])
  useEffect(() => {alive.current = true; return () => {alive.current = false; controller.current?.abort()}}, [])
  useEffect(() => {setFile(null); setResult(null); setVideoResult(null); setError(''); setMessage('');setDurationError('');setObservedCrop('');setPreviewError(false);setVideoDuration(0); if(input.current) input.current.value=''},[current])
  useEffect(() => {if(model?.available_crops.length && !model.available_crops.includes(crop)) setCrop(model.available_crops[0])}, [model,crop])
  useEffect(()=>{setDurationError(videoDuration>maxSeconds?`视频最长 ${maxSeconds} 秒，请截取后再上传。`:'')},[videoDuration,maxSeconds])
  function choose(next?: File) {
    if (!next || locked || !currentEnabled) return
    const image = ['image/jpeg','image/png','image/webp'].includes(next.type)
    if (current === 'image' && !image) {setError('请选择 JPG、PNG 或 WebP 图片。');return}
    if (current === 'image' && next.size > maxImage * 1024 * 1024) {setError(`图片最大 ${maxImage} MB，请压缩后重新选择。`);return}
    if (current === 'video' && !next.type.startsWith('video/')&&!/\.(mp4|mov|webm|avi)$/i.test(next.name)) {setError('请选择 MP4、MOV、WebM 或 AVI 视频。');return}
    if(current==='video'&&next.size>maxVideo*1024*1024){setError(`视频最大 ${maxVideo} MB，请压缩或截取后重试。`);return}
    setFile(next);setResult(null);setVideoResult(null);setError('');setMessage('');setDurationError('');setObservedCrop('');setPreviewError(false);setVideoDuration(0)
  }
  function recognized(cropName:string){setObservedCrop(cropName);onRecognized(cropName)}
  async function nativePhoto(){if(locked)return;setError('');try{const photo=await captureNativePhoto();if(photo)choose(photo)}catch(e){setError((e as Error).message)}}
  async function submit(event: FormEvent) {
    event.preventDefault();if(!file || busy || !currentEnabled || fileSizeError || (current==='video' && (!videoReady||durationError)))return
    setBusy(true);setError('');setResult(null);setVideoResult(null); const abort = new AbortController(); controller.current = abort
    setMessage(current==='video' ? '正在上传并按时间抽样识别视频。服务端处理完成后显示时间轴，请稍候…' : ready ? '正在识别作物与叶片状况…' : '正在保存采集样本…')
    const body=new FormData();body.append('file',file);if(plotId&&config.features.plots)body.append('plot_id',plotId);body.append('note',note);if(current==='image'&&!ready)body.append('crop',crop)
    try {
      if(current==='video') {const value=await api<VideoResult>('/media/video',{method:'POST',body,signal:abort.signal},180000);if(!alive.current)return;setVideoResult(value);setSelectedFrame(0);setMessage(`已完成 ${value.sampled_frames} 个时点的观察。`);if(value.results[0])recognized(value.results[0].detection.crop);onSaved()}
      else {const value=await api<Detection>('/detections',{method:'POST',body,signal:abort.signal},60000);if(!alive.current)return;setResult(value);setMessage(value.status==='awaiting_model'?'采集样本已保存。':`已自动识别为${value.crop}，观察已保存。`);recognized(value.crop);onSaved(value)}
    }catch(e){if(alive.current){if(abort.signal.aborted)setMessage('已停止等待。服务端可能继续处理，稍后可刷新检测记录。');else{setError((e as Error).message);setMessage('')}}}
    finally{if(alive.current)setBusy(false);controller.current=null}
  }
  return <div className="detect-page"><div className="page-intro"><span className="eyebrow">A CLOSER LOOK</span><h1>{observedCrop?`${observedCrop}检测室`:"看见叶片的小变化"}<Leaf size={21}/></h1><p>{observedCrop?"已跟随识别结果进入作物主题，继续查看本次观察。":"无需预选作物，识别后自动进入对应检测室。"}</p></div><div className="mode-switch" role="group" aria-label="选择检测方式">{modes.map(item=><button key={item.id} className={current===item.id?'active':''} aria-pressed={current===item.id} disabled={locked||!config.features[item.id==='image'?'image_detection':item.id==='video'?'video_detection':'live_detection']} onClick={()=>navigate(`detect/${item.id}`)}><item.icon size={18}/>{item.label}</button>)}</div>
    {!ready && <div className="info-note"><Leaf size={17}/><span>{model ? '识别模型尚未启用，可通过图片模式采集样本。视频与实时相机需启用模型。' : '正在读取识别服务状态，请稍候。'}</span></div>}
    {current!=="image"&&capabilityError&&<ErrorNote message={capabilityError} retry={()=>{setCapabilityError('');api<MediaCapabilities>('/media/capabilities').then(setCapabilities).catch(e=>setCapabilityError(e.message))}}/>}{current==='video'&&ready&&capabilities&&!capabilities.video_enabled&&<div className="info-note">视频解码服务尚未启用，请联系管理员安装媒体依赖。</div>}{current!=='image'&&!capabilities&&!capabilityError&&<p className="capture-message" role="status">正在确认媒体检测能力…</p>}{!currentEnabled&&<div className="info-note">管理员已暂停此检测方式。已有观察结果仍可在记录中阅读。</div>}<form onSubmit={submit}><fieldset disabled={locked}><div className="capture-meta"><label>关联地块<span>选填</span><select value={plotId} disabled={!config.features.plots} onChange={event=>setPlotId(event.target.value)}><option value="">暂不关联地块</option>{plots.map(plot=><option key={plot.id} value={plot.id}>{plot.name} · {plot.crop}</option>)}</select></label><label className="sample-note">采样备注<span>选填</span><input value={note} onChange={event=>setNote(event.target.value)} maxLength={500} placeholder="叶片位置、采样环境等"/></label>{!ready&&current==='image'&&<label>采集作物<select value={crop} onChange={event=>setCrop(event.target.value)}>{model?.available_crops.map(item=><option key={item}>{item}</option>)}</select></label>}</div></fieldset>
    {current!=='camera'&&<><div className={`upload-card ${file?'has-file':''}`}>
      <input ref={input} type="file" accept={current==='image'?'image/jpeg,image/png,image/webp':'video/mp4,video/quicktime,video/webm,video/x-msvideo,.mp4,.mov,.webm,.avi'} aria-label={current==='image'?'选择叶片图片':'选择作物视频'} className="visually-hidden" disabled={busy||!currentEnabled} onChange={event=>choose(event.target.files?.[0])}/>
      {file ? <>{current==='image'?<img className="selected-media" src={preview||undefined} alt="已选择的叶片照片"/>:<video className="selected-media" src={preview||undefined} controls playsInline preload="metadata" onError={()=>setPreviewError(true)} onLoadedMetadata={event=>{setPreviewError(false);const duration=event.currentTarget.duration;setVideoDuration(Number.isFinite(duration)?duration:0)}}/>}<button type="button" className="remove-media" aria-label="移除所选文件" disabled={busy} onClick={()=>{setFile(null);setResult(null);setVideoResult(null);if(input.current)input.current.value=''}}><X size={17}/></button><div className="selected-file"><span>{file.name}</span><small>{(file.size/1024/1024).toFixed(1)} MB</small></div></> : <><Art src={`/images/feature-${current}.webp`} alt={current==='image'?'小禾准备观察叶片':'小禾准备观察视频'} className="upload-art"/><h2>{current==='image'?'一张照片，开始观察':'把巡田过程，交给小禾'}</h2><p>{current==='image'?'自然光下拍清一片叶子，作物由模型自动识别。':'上传一段作物视频，按时间抽取画面分别识别。'}</p><button type="button" className="button primary" disabled={!currentEnabled} onClick={()=>input.current?.click()}><Upload size={17}/>{current==='image'?'选择叶片照片':'选择作物视频'}</button><small>{current==='image'?`JPG / PNG / WebP · 最大 ${maxImage} MB`:`最大 ${maxVideo} MB · ${maxSeconds} 秒 · 最多 ${maxFrames} 个时点`}</small></>}
    </div>{file&&<button type="button" className="text-button change-media" disabled={busy||!currentEnabled} onClick={()=>input.current?.click()}>重新选择{current==='image'?'图片':'视频'}</button>}
    {current==='image'&&isNativeAndroid()&&<button type="button" className="button outline full native-photo" onClick={nativePhoto} disabled={busy||!currentEnabled}><Camera size={17}/>直接拍一张叶片</button>}{previewError&&current==='video'&&<p className="capture-message" role="status">当前设备无法预览此格式，仍可上传分析。</p>}<ErrorNote message={error||durationError||fileSizeError}/>{message&&<p className="capture-message" role="status">{message}</p>}
    <button className="button primary full detect-submit" disabled={!file||busy||!model||!currentEnabled||!!fileSizeError||(current==='video'&&(!videoReady||!!durationError))}>{busy?<LoaderCircle size={18} className="spin"/>:<ScanLine size={18}/>} {busy?'正在处理，请稍候…':current==='video'?'开始视频观察':ready?'识别并保存':'保存采集样本'}</button>{busy&&<button type="button" className="button ghost full" onClick={()=>controller.current?.abort()}>取消等待</button>}</>}
    </form>
    {current==='camera'&&<CameraCapture ready={liveReady} plotId={plotId} note={note} onSaved={record=>{setResult(record);onSaved(record)}} onActive={setCameraActive} onRecognized={recognized} intervalMs={Math.max(capabilities?.frame_min_interval_ms??750,config.limits.frame_interval_ms)}/>}
    {result&&<section className="card result-card"><div className="section-heading"><h2><CheckCircle2 size={17}/>本次观察</h2><span>已保存</span></div><DetectionResult record={result} onAsk={onAsk}/></section>}
    {videoResult&&<section className="card video-results"><div className="section-heading"><h2>视频观察时间轴</h2><span>{formatTime(videoResult.duration_seconds)}</span></div><div className="video-summary"><span><strong>{videoResult.summary.total}</strong>观察时点</span><span><strong>{videoResult.summary.healthy}</strong>健康</span><span><strong>{videoResult.summary.attention}</strong>需关注</span></div><p className="fine-print">结果来自抽样画面，未覆盖视频的每一帧，可能遗漏短暂出现的异常。</p><div className="video-timeline">{videoResult.results.map((frame,index)=><button key={`${frame.timestamp_seconds}-${index}`} className={selectedFrame===index?'active':''} aria-pressed={selectedFrame===index} onClick={()=>{setSelectedFrame(index);recognized(frame.detection.crop)}}><Play size={12}/><strong>{formatFrameTime(frame.timestamp_seconds)}</strong><span>{frame.detection.crop}</span><Badge status={frame.detection.status}/></button>)}</div>{videoResult.results[selectedFrame]&&<DetectionResult record={videoResult.results[selectedFrame].detection} onAsk={onAsk}/>}</section>}
    <div className="photo-tips"><h3>给小禾一张更清楚的照片</h3><p>保留完整叶片，避开反光与阴影；一次观察一片叶子。{ready?`当前覆盖 ${model.supported_crops.length} 种作物。`:''}所选地块的作物须与识别结果一致。</p></div>
  </div>
}
