import {useEffect,useRef,useState} from 'react'
import {ChevronRight} from 'lucide-react'
import {DetectionResult,Empty,ErrorNote,Loading} from './components'
import {confidence} from './hooks'
import {IpIcon} from './IpIcon'
import {motionReduced} from './Motion'
import {getServiceBase,getToken} from './api'
import type {Detection} from './types'
import {taskFinished,type ManagedDetectionTask,type TaskRuntime} from './useDetectionTasks'
import './detection-tasks.css'

const statusLabels:Record<ManagedDetectionTask['status'],string>={reserving:'准备上传',awaiting_upload:'等待上传',uploading:'正在上传',checking:'正在确认状态',queued:'等待处理',processing:'正在处理',cancelling:'正在取消',completed:'结果已保存',cancelled:'已取消',failed:'未完成'}
export function DetectionTaskProgress({job,runtime,onOpen}:{job:ManagedDetectionTask;runtime:TaskRuntime;onOpen?:()=>void}){
  const [error,setError]=useState(''),[cancelling,setCancelling]=useState(false)
  const busy=useRef(false),mounted=useRef(true)
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  const percent=job.total_bytes?Math.min(100,Math.floor(job.uploaded_bytes/job.total_bytes*100)):0
  async function cancel(){if(busy.current||taskFinished(job)||job.status==='cancelling')return;busy.current=true;setCancelling(true);setError('');try{await runtime.cancel(job.key)}catch(reason){if(mounted.current)setError((reason as Error).message)}finally{busy.current=false;if(mounted.current)setCancelling(false)}}
  return <section className={`detection-task-progress task-${job.status}`} aria-label={`${job.filename}的检测任务`}>
    <header><IpIcon name={job.kind==='video'?'video':'detect'}/><div><strong>{job.filename}</strong><span>{statusLabels[job.status]}</span></div></header>
    {!taskFinished(job)&&<><progress max={job.total_bytes||1} value={job.uploaded_bytes} aria-label="文件上传进度"/><p className="task-progress-copy">上传 {percent}% · {(job.uploaded_bytes/1024/1024).toFixed(1)} / {(job.total_bytes/1024/1024).toFixed(1)} MB</p></>}
    {job.status==='queued'&&<p>文件已上传，可切换页面继续使用。</p>}{job.status==='processing'&&<p>正在处理已上传的文件，完成后会在任务中保留结果。</p>}{job.status==='cancelling'&&<p>正在等待服务端确认取消；尚未保存的结果不会写入观察记录。</p>}
    {job.status==='completed'&&<p>任务结果已保存。采集样本与识别结果以实际观察报告为准。</p>}
    {job.status==='cancelled'&&<p>本次任务已取消，可以重新选择文件。</p>}
    <ErrorNote message={job.error||error}/>
    <footer>{onOpen&&<button className="text-button" type="button" onClick={onOpen}>查看任务{job.status==='completed'?'结果':'进度'}<ChevronRight size={14}/></button>}{!taskFinished(job)&&<button className="text-button task-cancel" type="button" disabled={cancelling||job.status==='cancelling'} onClick={()=>void cancel()}>{cancelling||job.status==='cancelling'?'正在取消…':'取消任务'}</button>}</footer>
  </section>
}

export function DetectionTaskResult({job,runtime,visible=true,onAsk,onRecognized,onOpen}:{job:ManagedDetectionTask;runtime:TaskRuntime;visible?:boolean;onAsk?:(record:Detection)=>void;onRecognized?:(crop:string)=>void;onOpen?:()=>void}){
  const [records,setRecords]=useState<Detection[]>([]),[index,setIndex]=useState(0),[loading,setLoading]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0)
  const heading=useRef<HTMLHeadingElement>(null),reader=useRef(runtime.results);reader.current=runtime.results
  const owner=useRef({token:getToken(),base:getServiceBase()})
  const sameSession=()=>owner.current.token===getToken()&&owner.current.base===getServiceBase()
  const recognized=useRef(onRecognized);recognized.current=onRecognized
  useEffect(()=>{
    if(!visible||job.status!=='completed')return
    let current=true;const controller=new AbortController(),token=getToken(),base=getServiceBase();setLoading(true);setError('')
    const valid=()=>current&&!controller.signal.aborted&&getToken()===token&&getServiceBase()===base
    reader.current(job,controller.signal).then(rows=>{if(valid()){setRecords(rows);setIndex(0);const first=rows[0];if(first&&['healthy','attention'].includes(first.status))recognized.current?.(first.crop);requestAnimationFrame(()=>{if(valid()&&visible){heading.current?.focus({preventScroll:true});heading.current?.scrollIntoView({block:'start',behavior:motionReduced()?'instant':'smooth'})}})}}).catch(reason=>{if(valid())setError((reason as Error).message)}).finally(()=>{if(valid())setLoading(false)})
    return()=>{current=false;controller.abort()}
  },[job.key,job.status,visible,retry])
  const record=records[index]
  if(!sameSession())return null
  return <div className="detection-task-result"><DetectionTaskProgress job={job} runtime={runtime} onOpen={onOpen}/>{job.status==='completed'&&<>
    <h2 ref={heading} tabIndex={-1}>{record?.status==='awaiting_model'?'样本已保存':record?'本次检测完成':'查看本次结果'}</h2>
    {loading?<Loading text="正在读取这次任务的观察报告…"/>:<ErrorNote message={error} retry={()=>setRetry(value=>value+1)}/>}
    {records.length>1&&<><p className="fine-print">以下为视频抽样画面，不覆盖每一帧；实际时点见各条采样备注。</p><div className="task-frame-options" role="group" aria-label="选择视频采样画面">{records.map((item,i)=><button key={item.id} className={index===i?'active':''} aria-pressed={index===i} onClick={()=>{if(!sameSession())return;setIndex(i);if(['healthy','attention'].includes(item.status))recognized.current?.(item.crop)}}><strong>采样 {i+1}</strong><span>{item.crop} · {item.result||'样本已保存'}</span><small>{confidence(item.confidence)}</small></button>)}</div></>}
    {record&&<DetectionResult record={record} onAsk={record.status==='awaiting_model'||!onAsk?undefined:item=>{if(sameSession())onAsk(item)}}/>}
  </>}</div>
}

export default function DetectionTasksPage({runtime,onOpen}:{runtime:TaskRuntime;onOpen:(key:string)=>void}){
  const jobs=[...runtime.jobs].reverse(),active=jobs.filter(job=>!taskFinished(job)).length
  return <div className="detection-tasks-page"><div className="page-intro"><h1>我的检测任务</h1><p>{active?`${active} 项任务正在进行。`:'已提交的图片和视频会在这里保留本次会话的进度。'}切换页面不会停止上传与处理。</p></div><p className="info-note">同时最多上传两份文件。刷新、关闭应用或退出登录后不会继续保留这份本机队列。</p>{jobs.length?<div className="detection-task-list">{jobs.map(job=><DetectionTaskProgress key={job.key} job={job} runtime={runtime} onOpen={()=>onOpen(job.key)}/>)}</div>:<Empty title="暂时没有检测任务" text="选择图片、视频，或保存一帧相机观察后，可在这里查看进度。"/>}</div>
}
