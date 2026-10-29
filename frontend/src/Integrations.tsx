import {useEffect, useState, type FormEvent} from 'react'
import {api} from './api'
import {Modal} from './components'

export function IntegrationSettings() {
  const [data,setData]=useState<Record<string,unknown>|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{api<Record<string,unknown>>('/settings/integrations').then(setData).catch(e=>setError(e.message))},[])
  return <section className="panel integration-panel"><h2>注册、邮件与大模型配置</h2><p>在 backend/.env 修改配置并重启后端；Docker 使用项目根目录 .env。密钥仅在服务端保存。</p>{error?<p className="form-error">{error}</p>:data?<><div className="integration-grid">{[['开放注册','registration_enabled'],['邮箱验证码','email_verification_enabled'],['知识库 AI 问答','llm_enabled'],['邮件密码已配置','smtp_password_configured'],['大模型密钥已配置','llm_key_configured']].map(([name,key])=><div key={key}><span>{name}</span><b>{key.endsWith('_enabled')?(data[key]?'已开启':'未开启'):(data[key]?'已配置':'未配置')}</b><code>{({smtp_password_configured:'SMTP_PASSWORD',llm_key_configured:'LLM_API_KEY'}[key]||key.toUpperCase())}</code></div>)}</div><dl>{[['SMTP 服务','smtp_host'],['SMTP 端口','smtp_port'],['发信邮箱','smtp_from'],['传输加密','smtp_security'],['大模型 API 基础地址','llm_base_url'],['大模型名称','llm_model'],['权重上传上限 / MB','model_max_upload_mb']].map(([name,key])=><div key={key}><dt>{name}</dt><dd>{String(data[key]||'未配置')}</dd></div>)}</dl></>:<p>正在读取配置…</p>}</section>
}

interface Weight {id:string;name:string;filename:string;framework:string;size:number;sha256:string}
export function WeightManager({onChange,canManage}:{onChange:()=>void;canManage:boolean}) {
  const [items,setItems]=useState<Weight[]>([])
  const [limit,setLimit]=useState(200)
  const [open,setOpen]=useState(false)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [remove,setRemove]=useState<Weight|null>(null)
  const load=()=>api<{items:Weight[];max_upload_mb:number}>('/models').then(data=>{setItems(data.items);setLimit(data.max_upload_mb)}).catch(e=>setError(e.message))
  useEffect(()=>{void load()},[])
  async function upload(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError('');const body=new FormData(event.currentTarget);try{await api('/models',{method:'POST',body,signal:AbortSignal.timeout(300000)});setOpen(false);await load();onChange()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  async function erase(){if(!remove)return;setBusy(true);try{await api(`/models/${remove.id}`,{method:'DELETE'});setRemove(null);await load();onChange()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <section className="panel integration-panel"><div className="weight-heading"><div><h2>上传权重登记</h2><p>上传 YOLO / PyTorch 等训练产物。文件只保存并登记，推理适配后才能启用识别。</p></div>{canManage?<button className="button primary" onClick={()=>{setError('');setOpen(true)}}>添加模型权重</button>:<span className="quiet">管理员可添加与删除权重</span>}</div>{error&&!open&&<p className="form-error">{error}</p>}{items.length?<div className="weight-list">{items.map(item=><article key={item.id}><div><h3>{item.name}<span className="badge awaiting_model">待验证与适配</span></h3><p>{item.filename} · {item.framework} · {(item.size/1048576).toFixed(2)} MB</p><code title={item.sha256}>SHA256 {item.sha256}</code></div><>{canManage&&<button className="text-button danger-text" onClick={()=>setRemove(item)}>删除</button>}</></article>)}</div>:<div className="empty"><h3>暂无额外上传登记</h3><p>支持 .pt、.pth、.onnx、.safetensors、.h5、.keras，最大 {limit} MB。</p></div>}{open&&<Modal title="添加训练模型" onClose={()=>!busy&&setOpen(false)}><form className="modal-form" onSubmit={upload}><label>模型名称<input name="name" required maxLength={100} placeholder="例如：番茄病害 YOLO v1"/></label><label>训练框架<input name="framework" defaultValue="PyTorch / YOLO" required maxLength={80}/></label><label>训练权重文件（最大 {limit} MB）<input type="file" name="file" required accept=".pt,.pth,.onnx,.safetensors,.h5,.keras" onChange={e=>{const f=e.target.files?.[0];if(f&&f.size>limit*1048576){e.target.value='';setError(`文件不能超过 ${limit} MB`)}}}/></label><p className="quiet">保留原始文件并记录 SHA256；不自动反序列化或执行 PT 文件。</p>{error&&<p className="form-error">{error}</p>}<button className="button primary" disabled={busy}>{busy?'正在上传，请勿关闭…':'上传并登记'}</button></form></Modal>}{remove&&<Modal title="删除权重" onClose={()=>!busy&&setRemove(null)}><div className="modal-form"><p>删除「{remove.name}」的登记及权重文件？此操作不可撤销。</p><button className="button danger" disabled={busy} onClick={erase}>确认删除</button></div></Modal>}</section>
}
