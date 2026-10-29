export type DetectionTaskStatus='awaiting_upload'|'uploading'|'queued'|'processing'|'cancelling'|'completed'|'cancelled'|'failed'
export interface DetectionTask {
  id:string;client_request_id:string;kind:'image'|'video';filename:string;status:DetectionTaskStatus
  received_bytes:number;total_bytes:number;created_at:string;updated_at:string;error:string|null;result_ids:string[]
}
export interface ManagedDetectionTask {
  key:string;filename:string;kind:'image'|'video';status:DetectionTaskStatus|'reserving'|'checking'
  uploaded_bytes:number;total_bytes:number;created_at:string;error:string|null;task:DetectionTask|null
}
export interface DetectionTaskInput {file:File;kind:'image'|'video';note?:string;plot_id?:string;crop?:string}
interface Options {
  apiBaseUrl:string;token:string;isCurrent:()=>boolean;onUnauthorized?:()=>void
  fetcher?:typeof fetch;xhrFactory?:()=>XMLHttpRequest;pollIntervalMs?:number;uploadTimeoutMs?:number
}
interface Entry {view:ManagedDetectionTask;input:Omit<DetectionTaskInput,'file'>;file:File|null;started:boolean;uploadAttempted:boolean;cancelRequested:boolean;cancelInFlight?:boolean;retryAt?:number;missing:number;uncertain:boolean;xhr?:XMLHttpRequest;xhrActive?:boolean}
class TaskError extends Error {constructor(message:string,readonly status=0,readonly retryAfterMs=0){super(message)}}
const terminal=(status:ManagedDetectionTask['status'])=>['completed','cancelled','failed'].includes(status)
const serverStage:Record<DetectionTaskStatus,number>={awaiting_upload:0,uploading:1,queued:2,processing:3,cancelling:4,completed:5,cancelled:5,failed:5}

/** One in-memory account/session queue, independent of routes and application frameworks. */
export class DetectionTaskManager {
  private readonly base:string
  private readonly token:string
  private readonly fetcher:typeof fetch
  private readonly entries=new Map<string,Entry>()
  private readonly listeners=new Set<(jobs:readonly ManagedDetectionTask[])=>void>()
  private readonly controllers=new Set<AbortController>()
  private disposed=false
  private activeUploads=0
  private polling=false
  private pollTimer:ReturnType<typeof setTimeout>|undefined
  constructor(private readonly options:Options){
    const url=new URL(options.apiBaseUrl)
    if(!['https:','http:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error('检测服务地址无效。')
    this.base=url.href.replace(/\/+$/,'');this.token=options.token;this.fetcher=options.fetcher??globalThis.fetch.bind(globalThis)
  }
  private current(){return !this.disposed&&this.options.isCurrent()}
  private confirmedTerminal(entry:Entry){return Boolean(entry.view.task&&terminal(entry.view.task.status))}
  private uploadAccepted(entry:Entry){return Boolean(entry.view.task&&serverStage[entry.view.task.status]>=serverStage.queued)}
  private recoverReservation(entry:Entry){if(!entry.view.task)return false;entry.uncertain=false;this.apply(entry,entry.view.task);return true}
  getSnapshot():readonly ManagedDetectionTask[]{return [...this.entries.values()].map(({view})=>({...view,task:view.task?{...view.task,result_ids:[...view.task.result_ids]}:null}))}
  subscribe(listener:(jobs:readonly ManagedDetectionTask[])=>void){this.listeners.add(listener);listener(this.getSnapshot());return()=>{this.listeners.delete(listener)}}
  private publish(){if(!this.current())return;const snapshot=this.getSnapshot();for(const listener of this.listeners)listener(snapshot)}
  enqueue(input:DetectionTaskInput){
    if(!this.current())throw new Error('账户或服务已变化，请重新登录后提交。')
    if(!input.file.size)throw new Error('文件为空，请重新选择。')
    const key=crypto.randomUUID(),{file,...metadata}=input
    this.entries.set(key,{view:{key,filename:file.name,kind:input.kind,status:'reserving',uploaded_bytes:0,total_bytes:file.size,created_at:new Date().toISOString(),error:null,task:null},input:{...metadata},file,started:false,uploadAttempted:false,cancelRequested:false,missing:0,uncertain:false})
    this.publish();this.pump();this.schedulePoll();return key
  }
  private async request<T>(path:string,init:RequestInit={},cleanup=false):Promise<T>{
    if(!cleanup&&!this.current())throw new TaskError('检测会话已结束。')
    const controller=new AbortController();this.controllers.add(controller)
    const timeout=setTimeout(()=>controller.abort(),15000)
    try{
      const response=await this.fetcher(this.base+path,{...init,headers:{'Content-Type':'application/json',Authorization:`Bearer ${this.token}`,...init.headers},cache:'no-store',redirect:'error',signal:controller.signal,keepalive:cleanup})
      if(!response.ok){
        if(response.status===401&&this.current())this.options.onUnauthorized?.()
        const body=await response.json().catch(()=>({}))
        throw new TaskError(typeof body.detail==='string'?body.detail:response.status===429?'检测队列已满，请稍后重新提交。':`检测任务请求未完成（${response.status}）。`,response.status)
      }
      return await response.json() as T
    }finally{clearTimeout(timeout);this.controllers.delete(controller)}
  }
  private apply(entry:Entry,task:DetectionTask){
    if(!this.current())return
    if(entry.view.task&&terminal(entry.view.task.status)&&entry.view.task.status!==task.status)return
    if(entry.view.task&&serverStage[task.status]<serverStage[entry.view.task.status])return
    const localUpload=Boolean(entry.xhrActive&&entry.xhr&&!entry.uncertain&&!entry.cancelRequested&&['awaiting_upload','uploading'].includes(task.status))
    entry.view.task=task;entry.missing=0
    entry.view.status=entry.cancelRequested&&!terminal(task.status)?'cancelling':entry.uncertain&&['awaiting_upload','uploading'].includes(task.status)?'checking':localUpload&&task.status==='awaiting_upload'?'uploading':task.status
    entry.view.uploaded_bytes=localUpload?Math.max(entry.view.uploaded_bytes,task.received_bytes):task.received_bytes
    entry.view.error=task.error??(entry.retryAt&&task.status==='awaiting_upload'?'上传通道繁忙，稍后会重试同一任务。':entry.uncertain&&entry.view.status==='checking'?'上传连接已中断，正在确认服务器状态。':null)
    if(serverStage[task.status]>=serverStage.queued){entry.file=null;entry.uncertain=false}
    this.publish()
  }
  private fail(entry:Entry,message:string){if(!this.current()||(entry.view.task&&terminal(entry.view.task.status)))return;entry.view.status='failed';entry.view.error=message;entry.file=null;entry.uncertain=false;this.publish()}
  private pump(){
    if(!this.current())return
    for(const entry of this.entries.values()){
      if(this.activeUploads>=2)break
      if(entry.started||entry.cancelRequested||!entry.file||terminal(entry.view.status)||entry.uploadAttempted||entry.uncertain||(entry.retryAt??0)>Date.now())continue
      if(entry.view.task&&entry.view.task.status!=='awaiting_upload')continue
      entry.started=true;this.activeUploads++
      void this.run(entry).finally(()=>{entry.started=false;this.activeUploads--;this.pump();this.schedulePoll()})
    }
  }
  private async run(entry:Entry){
    try{
      if(!entry.view.task){
        try{
          const task=await this.request<DetectionTask>('/detection-tasks',{method:'POST',body:JSON.stringify({...entry.input,client_request_id:entry.view.key,filename:entry.file!.name,content_type:entry.file!.type||'application/octet-stream',size_bytes:entry.file!.size})})
          if(!this.current()){void this.cancelRemote(task.id);return}
          this.apply(entry,task)
        }catch(reason){
          if(!this.current())return
          if(this.confirmedTerminal(entry))return
          // A GET may confirm the UUID while the original POST response is still pending.
          if(!this.recoverReservation(entry)){
            if(reason instanceof TaskError&&reason.status){this.fail(entry,reason.message);return}
            entry.uncertain=true;entry.view.status='checking';entry.view.error='正在确认任务是否已创建，不会重复提交。';this.publish();return
          }
        }
      }
      if(!this.current())return
      if(entry.cancelRequested){await this.cancel(entry.view.key);return}
      const task=entry.view.task!
      if(task.status!=='awaiting_upload')return
      entry.uploadAttempted=true;entry.retryAt=undefined;entry.view.status='uploading';entry.view.error=null;this.publish()
      let retainFile=false
      try{
        const updated=await this.upload(entry,task.id)
        if(this.current())this.apply(entry,updated)
      }catch(reason){
        if(!this.current()||entry.cancelRequested)return
        if(this.uploadAccepted(entry))return
        entry.view.uploaded_bytes=entry.view.task?.received_bytes??0
        if(reason instanceof TaskError&&reason.status===429){
          retainFile=true;entry.uploadAttempted=false;entry.retryAt=Date.now()+(reason.retryAfterMs||5000);entry.view.status='awaiting_upload';entry.view.error='上传通道繁忙，稍后会重试同一任务。';this.publish();return
        }
        entry.uncertain=true;entry.view.status='checking';entry.view.error='上传连接已中断，正在确认服务器状态。';this.publish()
        await this.refreshOne(entry)
      }finally{if(!retainFile)entry.file=null;entry.xhrActive=false;entry.xhr=undefined}
    }catch(reason){if(this.current())this.fail(entry,(reason as Error).message)}
  }
  private upload(entry:Entry,id:string):Promise<DetectionTask>{
    return new Promise((resolve,reject)=>{
      const xhr=this.options.xhrFactory?.()??new XMLHttpRequest();entry.xhr=xhr;entry.xhrActive=true
      const settled=()=>{if(entry.xhr===xhr)entry.xhrActive=false}
      xhr.open('PUT',`${this.base}/detection-tasks/${encodeURIComponent(id)}/file`)
      xhr.setRequestHeader('Authorization',`Bearer ${this.token}`);xhr.setRequestHeader('Content-Type',entry.file!.type||'application/octet-stream')
      xhr.timeout=this.options.uploadTimeoutMs??600000
      xhr.upload.onprogress=event=>{if(this.current()&&entry.xhr===xhr&&entry.xhrActive&&!entry.cancelRequested&&!entry.uncertain&&['awaiting_upload','uploading'].includes(entry.view.task?.status??'')){entry.view.uploaded_bytes=Math.min(entry.view.total_bytes,Math.max(entry.view.task?.received_bytes??0,event.loaded));this.publish()}}
      xhr.onload=()=>{
        settled()
        if(xhr.status>=200&&xhr.status<300){try{resolve(JSON.parse(xhr.responseText) as DetectionTask)}catch{reject(new TaskError('上传响应未确认。'))}}
        else{if(xhr.status===401&&this.current())this.options.onUnauthorized?.();const retryAfter=Math.min(60000,Math.max(1000,Number(xhr.getResponseHeader?.('Retry-After')||'5')*1000));reject(new TaskError('上传响应未确认。',xhr.status,retryAfter))}
      }
      xhr.onerror=()=>{settled();reject(new TaskError('上传连接已中断。'))};xhr.ontimeout=()=>{settled();reject(new TaskError('上传等待超时。'))};xhr.onabort=()=>{settled();reject(new TaskError('上传已停止。'))}
      xhr.send(entry.file)
    })
  }
  private schedulePoll(){
    if(!this.current()||this.pollTimer!==undefined||![...this.entries.values()].some(entry=>!terminal(entry.view.status)))return
    this.pollTimer=setTimeout(()=>{this.pollTimer=undefined;void this.refresh().finally(()=>this.schedulePoll())},this.options.pollIntervalMs??2000)
  }
  private async refreshOne(entry:Entry){
    if(!entry.view.task)return
    try{this.apply(entry,await this.request<DetectionTask>(`/detection-tasks/${encodeURIComponent(entry.view.task.id)}`))}
    catch(reason){if(reason instanceof TaskError&&reason.status===404)this.fail(entry,'服务已重启或任务已失效，请重新选择文件提交。')}
  }
  async refresh(){
    if(!this.current()||this.polling)return
    this.polling=true
    try{
      const tasks=await this.request<DetectionTask[]>('/detection-tasks')
      if(!this.current())return
      for(const entry of this.entries.values()){
        if(terminal(entry.view.status))continue
        const task=tasks.find(value=>value.client_request_id===entry.view.key)
        if(task){
          const pendingCreation=!entry.view.task
          if(pendingCreation)entry.uncertain=false
          this.apply(entry,task)
          if(entry.cancelRequested&&!terminal(task.status))void this.cancel(entry.view.key)
        }else if(entry.view.task)await this.refreshOne(entry)
        else if(entry.uncertain&&++entry.missing>=3)this.fail(entry,'未能确认任务创建结果，请重新选择文件；没有自动重复提交。')
      }
      this.pump()
    }catch{
      if(this.current())for(const entry of this.entries.values())if(!terminal(entry.view.status)){entry.view.error='暂时无法刷新任务状态，恢复连接后会继续确认。';this.publish()}
    }finally{this.polling=false}
  }
  private async cancelRemote(id:string){try{return await this.request<DetectionTask>(`/detection-tasks/${encodeURIComponent(id)}`,{method:'DELETE'},true)}catch{return null}}
  async cancel(key:string){
    const entry=this.entries.get(key)
    if(!entry||!this.current()||terminal(entry.view.status))return
    entry.cancelRequested=true;entry.view.uploaded_bytes=entry.view.task?.received_bytes??0
    if(!entry.view.task){
      if(!entry.started&&!entry.uncertain){entry.view.status='cancelled';entry.file=null;this.publish();return}
      entry.view.status='cancelling';entry.view.error='正在确认并取消服务器任务。';this.publish();return
    }
    if(entry.cancelInFlight)return
    entry.cancelInFlight=true;entry.view.status='cancelling';entry.view.error=null;this.publish()
    // Let the server set its cancellation flag before ending the request body.
    // Aborting first can turn an intentional cancel into an upload-disconnect failure.
    const xhr=entry.xhr
    let task:DetectionTask|null=null
    try{task=await this.cancelRemote(entry.view.task.id)}
    finally{
      if(entry.xhr===xhr){xhr?.abort();entry.xhrActive=false;entry.xhr=undefined}
      entry.file=null;entry.cancelInFlight=false
    }
    if(!this.current())return
    if(task)this.apply(entry,task)
    else{entry.view.error='取消请求未确认，正在刷新服务器状态。';this.publish()}
    this.schedulePoll()
  }
  dispose(){
    if(this.disposed)return
    this.disposed=true;if(this.pollTimer!==undefined)clearTimeout(this.pollTimer);this.pollTimer=undefined
    for(const controller of this.controllers)controller.abort()
    const unresolved=new Set<string>()
    for(const entry of this.entries.values()){
      entry.xhr?.abort();entry.file=null
      if(entry.view.task&&!terminal(entry.view.task.status))void this.cancelRemote(entry.view.task.id)
      else if(!entry.view.task&&(entry.started||entry.uncertain))unresolved.add(entry.view.key)
    }
    if(unresolved.size)void this.request<DetectionTask[]>('/detection-tasks',{},true).then(tasks=>{for(const task of tasks)if(unresolved.has(task.client_request_id)&&!terminal(task.status))void this.cancelRemote(task.id)}).catch(()=>{})
    this.listeners.clear();this.entries.clear()
  }
}
