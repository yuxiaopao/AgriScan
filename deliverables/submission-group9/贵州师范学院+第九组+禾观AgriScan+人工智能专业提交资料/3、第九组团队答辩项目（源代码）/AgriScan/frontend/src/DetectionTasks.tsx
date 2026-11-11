import {useEffect,useRef,useState} from 'react'
import {CircleAlert,ClipboardList,LoaderCircle,X} from 'lucide-react'
import {DetectionTaskManager,type ManagedDetectionTask} from '../../shared/detectionTasks'
import {api,apiUrl,getToken,setToken} from './api'
import {Modal} from './components'
import type {Detection} from './types'
import './detection-tasks.css'

export const taskLabels:Record<ManagedDetectionTask['status'],string>={reserving:'正在建立任务',checking:'正在核对状态',awaiting_upload:'等待上传',uploading:'正在上传',queued:'排队检测',processing:'正在检测',cancelling:'正在取消',completed:'任务已完成',cancelled:'已取消',failed:'检测未完成'}
export const taskFinished=(job:ManagedDetectionTask)=>['completed','cancelled','failed'].includes(job.status)
export function useDetectionTasks(token:string|null,onCompleted:(record:Detection,job:ManagedDetectionTask)=>void){
  const callback=useRef(onCompleted);callback.current=onCompleted
  const scope=useRef<{token:string;manager:DetectionTaskManager}|null>(null)
  const [manager,setManager]=useState<DetectionTaskManager|null>(null),[jobs,setJobs]=useState<readonly ManagedDetectionTask[]>([])
  const [selectedKey,setSelectedKey]=useState<string|null>(null),[viewVersion,setViewVersion]=useState(0),[records,setRecords]=useState<Record<string,Detection>>({}),[errors,setErrors]=useState<Record<string,string>>({})
  const loadRef=useRef<(job:ManagedDetectionTask)=>void>(()=>{})
  useEffect(()=>{
    setJobs([]);setRecords({});setErrors({});setSelectedKey(null);setManager(null)
    if(!token)return
    let alive=true
    const fetched=new Map<string,Detection>(),pending=new Set<string>(),announced=new Set<string>(),attempted=new Set<string>()
    const current=()=>alive&&getToken()===token&&scope.current?.manager===instance
    const instance=new DetectionTaskManager({apiBaseUrl:new URL(apiUrl(''),window.location.origin).href,token,isCurrent:()=>alive&&getToken()===token,
      onUnauthorized:()=>{if(current()){setToken(null);window.dispatchEvent(new Event('agriscan-auth-expired'))}}})
    scope.current={token,manager:instance};setManager(instance)
    const load=(job:ManagedDetectionTask)=>{
      const id=job.task?.result_ids[0]
      if(!current()||!id||fetched.has(job.key)||pending.has(job.key))return
      pending.add(job.key);attempted.add(job.key);setErrors(old=>({...old,[job.key]:''}))
      void api<Detection>(`/detections/${encodeURIComponent(id)}`).then(record=>{
        if(!current())return
        fetched.set(job.key,record);setRecords(old=>({...old,[job.key]:record}))
        if(!announced.has(job.key)){announced.add(job.key);callback.current(record,job)}
      }).catch(reason=>{if(current())setErrors(old=>({...old,[job.key]:(reason as Error).message}))}).finally(()=>pending.delete(job.key))
    }
    loadRef.current=load
    const unsubscribe=instance.subscribe(snapshot=>{if(!current())return;setJobs(snapshot);for(const job of snapshot)if(job.status==='completed'&&!attempted.has(job.key))load(job)})
    const check=()=>{if(!current()){instance.dispose();if(alive){setJobs([]);setRecords({});setErrors({});setSelectedKey(null);setManager(null)}}}
    window.addEventListener('storage',check);window.addEventListener('focus',check)
    return()=>{alive=false;unsubscribe();instance.dispose();if(scope.current?.manager===instance)scope.current=null;loadRef.current=()=>{};window.removeEventListener('storage',check);window.removeEventListener('focus',check)}
  },[token])
  const valid=scope.current?.token===token&&getToken()===token
  return {manager:valid?manager:null,jobs:valid?jobs:[],selectedKey:valid?selectedKey:null,viewVersion:valid?viewVersion:0,records:valid?records:{},errors:valid?errors:{},
    select:(key:string|null)=>{if(!valid)return;setSelectedKey(key);if(key)setViewVersion(value=>value+1);const job=jobs.find(value=>value.key===key);if(job?.status==='completed')loadRef.current(job)}}
}
export type DetectionTasksBinding=ReturnType<typeof useDetectionTasks>

export function DetectionTaskProgress({job}:{job:ManagedDetectionTask}){
  const percent=Math.min(100,Math.round(job.uploaded_bytes/Math.max(1,job.total_bytes)*100))
  return <div className="detection-task-progress" role="status"><strong>{!taskFinished(job)&&<LoaderCircle size={15} className="spin"/>}{taskLabels[job.status]}</strong>{job.status==='uploading'&&<><progress max={job.total_bytes} value={job.uploaded_bytes} aria-label={`${job.filename}上传进度`}/><span>已上传 {percent}%</span></>}{['queued','processing','checking','cancelling'].includes(job.status)&&<p>{job.status==='cancelling'?'正在等待服务器确认，最终状态以服务器返回为准。':job.status==='checking'?'正在核对原任务，不会自动创建重复检测。':'可以切换到其他模块，任务会继续；完成后可在任务中心查看。'}</p>}{job.error&&<p className="detection-task-error"><CircleAlert size={14}/>{job.error}</p>}</div>
}
export function DetectionTaskCenter({tasks,onView}:{tasks:DetectionTasksBinding;onView:(key:string)=>void}){
  const [open,setOpen]=useState(false),active=tasks.jobs.filter(job=>!taskFinished(job)).length
  return <><button className="detection-task-entry" type="button" onClick={()=>setOpen(true)} aria-label={`检测任务，${active}项进行中`}><ClipboardList size={17}/><span>检测任务</span>{active>0&&<b>{active}</b>}</button>{open&&<Modal title="我的检测任务" onClose={()=>setOpen(false)}><div className="detection-task-center"><p>切换工作空间模块时会继续上传与检测。请保持当前程序和登录会话。</p>{!tasks.jobs.length&&<p className="quiet">还没有本次会话的检测任务。</p>}{[...tasks.jobs].reverse().map(job=><article key={job.key}><header><strong title={job.filename}>{job.filename}</strong><time>{new Date(job.created_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</time></header><DetectionTaskProgress job={job}/><footer><button type="button" className="text-button" onClick={()=>{onView(job.key);setOpen(false)}}>{job.status==='completed'?'查看结果':'查看任务'}</button>{!taskFinished(job)&&<button type="button" className="text-button" disabled={job.status==='cancelling'} onClick={()=>void tasks.manager?.cancel(job.key)}><X size={13}/>取消任务</button>}</footer></article>)}</div></Modal>}</>
}
