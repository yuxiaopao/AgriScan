import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {fileURLToPath} from 'node:url'
import {runInThisContext} from 'node:vm'

const sourceUrl=new URL('../detectionTasks.ts',import.meta.url)
const requireFrontend=createRequire(new URL('../../frontend/package.json',import.meta.url))
const ts=requireFrontend('typescript')
const compiled=ts.transpileModule(readFileSync(sourceUrl,'utf8'),{
  compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS},
  fileName:fileURLToPath(sourceUrl),
}).outputText
const loadCore=runInThisContext(`(function(exports,setTimeout,clearTimeout,Date){${compiled}\n})`,{
  filename:fileURLToPath(sourceUrl),
})

// Drain bounded promise continuations without real sleeps or provider requests.
async function settle(){for(let i=0;i<40;i++)await Promise.resolve()}
const file=(name='leaf.jpg',type='image/jpeg')=>new File(['x'.repeat(100)],name,{type})
const input=(name='leaf.jpg')=>({file:file(name),kind:'image',note:'Original observation'})

function fixture(t,options={}){
  let now=Date.UTC(2026,9,29),nextTimer=0,nextTask=0,current=true,listFails=false
  const timers=new Map(),server=new Map(),requests=[],uploads=[],heldPosts=new Map(),heldDeletes=new Map()
  const clock={
    setTimeout(callback,delay){const id=++nextTimer;timers.set(id,{callback,at:now+delay});return id},
    clearTimeout(id){timers.delete(id)},
    async advance(ms){
      const target=now+ms
      for(let count=0;;count++){
        assert(count<1000,'timer scheduling must settle')
        const due=[...timers].filter(([,timer])=>timer.at<=target).sort((a,b)=>a[1].at-b[1].at)[0]
        if(!due)break
        now=due[1].at;timers.delete(due[0]);due[1].callback();await settle()
      }
      now=target;await settle()
    },
  }
  class ClockDate extends Date {
    constructor(...args){super(...(args.length?args:[now]))}
    static now(){return now}
  }
  const exported={};loadCore(exported,clock.setTimeout,clock.clearTimeout,ClockDate)
  const response=(value,status=200)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(value)})
  function deferred(signal,collection,key){
    return new Promise((resolve,reject)=>{
      const abort=()=>{collection.delete(key);reject(new DOMException('Synthetic cancellation','AbortError'))}
      const finish=callback=>value=>{signal?.removeEventListener('abort',abort);collection.delete(key);callback(value)}
      collection.set(key,{resolve:finish(resolve),reject:finish(reject)})
      if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true})
    })
  }
  const fetcher=async(url,init={})=>{
    const method=init.method??'GET';requests.push({url,method,headers:init.headers,body:init.body})
    if(method==='POST'){
      const body=JSON.parse(init.body),task={
        id:`task-${++nextTask}`,client_request_id:body.client_request_id,filename:body.filename,kind:body.kind,
        status:'awaiting_upload',received_bytes:0,total_bytes:body.size_bytes,
        created_at:new ClockDate().toISOString(),updated_at:new ClockDate().toISOString(),error:null,result_ids:[],
      }
      server.set(task.id,task)
      if(options.holdPost)return deferred(init.signal,heldPosts,task.client_request_id)
      if(options.losePost)throw new Error('Synthetic lost reservation response')
      return response(task,201)
    }
    if(method==='DELETE'){
      const task=server.get(url.split('/').at(-1))
      if(!task)return response({},404)
      if(options.holdDelete)return deferred(init.signal,heldDeletes,task.client_request_id)
      task.status=options.commitWins?'completed':options.pendingCancel?'cancelling':'cancelled'
      task.result_ids=options.commitWins?['saved-record']:[]
      return response(task)
    }
    if(url.endsWith('/detection-tasks')){
      if(listFails)throw new Error('Synthetic poll timeout')
      return response([...server.values()])
    }
    const task=server.get(url.split('/').at(-1))
    return task?response(task):response({},404)
  }
  const xhrFactory=()=>({
    upload:{},headers:{},active:false,status:0,responseText:'',
    open(method,url){this.method=method;this.url=url},
    setRequestHeader(name,value){this.headers[name]=value},
    getResponseHeader(){return '5'},
    send(body){this.body=body;this.active=true;uploads.push(this)},
    progress(loaded){this.upload.onprogress?.({loaded})},
    abort(){
      if(this.active){
        this.active=false
        const task=server.get(this.url.split('/').at(-2))
        if(options.disconnectFails&&task&&['awaiting_upload','uploading'].includes(task.status)){
          task.status='failed';task.error='Synthetic upload disconnected before cancellation'
        }
        this.onabort?.()
      }
    },
    lose(){assert(this.active);this.active=false;this.onerror?.()},
    reply(status=202){
      assert(this.active);this.active=false;this.status=status
      this.responseText=JSON.stringify(server.get(this.url.split('/').at(-2)))
      this.onload?.()
    },
    finish(status='queued'){
      const task=server.get(this.url.split('/').at(-2));assert(task)
      task.status=status;task.received_bytes=task.total_bytes;this.reply()
    },
  })
  const manager=new exported.DetectionTaskManager({
    apiBaseUrl:'https://service-a.invalid/agriscan/api',token:'SyntheticSessionA',isCurrent:()=>current,
    fetcher,xhrFactory,pollIntervalMs:999999,
  })
  t.after(async()=>{
    manager.dispose();await settle()
    assert.equal(timers.size,0,'dispose must clear poll/request timers, including cleanup requests')
    assert.equal(uploads.filter(xhr=>xhr.active).length,0,'dispose must abort active upload transports')
    assert.equal(heldPosts.size+heldDeletes.size,0,'dispose must release pending controlled requests')
  })
  return {
    manager,server,requests,uploads,clock,
    view:key=>manager.getSnapshot().find(job=>job.key===key),
    task:key=>[...server.values()].find(task=>task.client_request_id===key),
    async poll(){await manager.refresh();await settle()},
    setCurrent(value){current=value},setListFailure(value){listFails=value},
    rejectPost(key){assert(heldPosts.has(key));heldPosts.get(key).reject(new Error('Synthetic lost POST response'))},
    rejectDelete(key){assert(heldDeletes.has(key));heldDeletes.get(key).reject(new Error('Synthetic lost DELETE response'))},
    resolveDelete(key,status='cancelled'){
      const task=[...server.values()].find(task=>task.client_request_id===key);task.status=status
      assert(heldDeletes.has(key));heldDeletes.get(key).resolve(response(task))
    },
    postCount:()=>requests.filter(request=>request.method==='POST').length,
    deleteCount:()=>requests.filter(request=>request.method==='DELETE').length,
  }
}

test('active XHR retains uploading and local progress while a buffered server still awaits the body',async t=>{
  const e=fixture(t),key=e.manager.enqueue(input());await settle()
  for(const bytes of [55,100]){
    e.uploads[0].progress(bytes);await e.poll()
    assert.equal(e.view(key).status,'uploading');assert.equal(e.view(key).uploaded_bytes,bytes)
    assert.equal(e.view(key).task.status,'awaiting_upload')
  }
  e.setListFailure(true);await e.poll()
  assert.equal(e.view(key).status,'uploading');assert.equal(e.view(key).uploaded_bytes,100);assert(e.view(key).error)
  e.setListFailure(false);await e.poll();assert.equal(e.view(key).error,null)
  assert.equal(e.postCount(),1);assert.equal(e.uploads.length,1)
})

test('GET can recover a reservation before its original POST times out, then upload once to that ID',async t=>{
  const e=fixture(t,{holdPost:true}),key=e.manager.enqueue(input());await settle();await e.poll()
  const id=e.view(key).task.id
  await e.clock.advance(15000)
  assert.equal(e.view(key).status,'uploading');assert.equal(e.postCount(),1);assert.equal(e.uploads.length,1)
  assert(e.uploads[0].url.endsWith(`/${id}/file`))
})

for(const status of ['queued','processing'])test(`GET-confirmed ${status} before a POST failure is tracked without another PUT`,async t=>{
  const e=fixture(t,{holdPost:true}),key=e.manager.enqueue(input());await settle()
  Object.assign(e.task(key),{status,received_bytes:100});await e.poll();e.rejectPost(key);await settle()
  assert.equal(e.view(key).status,status);assert.equal(e.uploads.length,0);assert.equal(e.postCount(),1)
})

test('cancel during reservation takes priority when GET finds the task before the POST fails',async t=>{
  const e=fixture(t,{holdPost:true,holdDelete:true}),key=e.manager.enqueue(input());await settle()
  await e.manager.cancel(key);await e.poll();e.rejectPost(key);await settle()
  assert.equal(e.view(key).status,'cancelling');assert.equal(e.uploads.length,0);assert.equal(e.deleteCount(),1)
  e.resolveDelete(key);await settle();assert.equal(e.view(key).status,'cancelled');assert.equal(e.postCount(),1)
})

test('failed XHR uses confirmed server bytes while checking instead of optimistic local bytes',async t=>{
  const e=fixture(t),key=e.manager.enqueue(input());await settle();e.uploads[0].progress(55)
  Object.assign(e.task(key),{status:'uploading',received_bytes:20});e.uploads[0].lose();await settle()
  assert.equal(e.view(key).status,'checking');assert.equal(e.view(key).uploaded_bytes,20)
  assert.equal(e.postCount(),1);assert.equal(e.uploads.length,1)
})

test('429 preserves the file and reservation, resets unconfirmed progress, then retries only PUT after backoff',async t=>{
  const e=fixture(t),original=input(),key=e.manager.enqueue(original);await settle()
  e.uploads[0].progress(55);e.uploads[0].reply(429);await settle()
  assert.equal(e.view(key).status,'awaiting_upload');assert.equal(e.view(key).uploaded_bytes,0)
  await e.clock.advance(4999);await e.poll();assert.equal(e.uploads.length,1)
  await e.clock.advance(1);await e.poll();assert.equal(e.uploads.length,2);assert.equal(e.uploads[1].body,original.file)
  assert.equal(e.postCount(),1);assert.equal(e.uploads[0].url,e.uploads[1].url)
})

test('server-confirmed processing bytes cannot be downgraded by late progress or stale awaiting snapshots',async t=>{
  const e=fixture(t),key=e.manager.enqueue(input());await settle()
  Object.assign(e.task(key),{status:'processing',received_bytes:100});await e.poll();e.uploads[0].progress(55)
  assert.equal(e.view(key).status,'processing');assert.equal(e.view(key).uploaded_bytes,100)
  Object.assign(e.task(key),{status:'awaiting_upload',received_bytes:0});await e.poll()
  assert.equal(e.view(key).status,'processing');assert.equal(e.view(key).uploaded_bytes,100)
})

test('confirmed completion and saved IDs survive late XHR progress/error and later task disappearance',async t=>{
  const e=fixture(t),key=e.manager.enqueue(input());await settle()
  Object.assign(e.task(key),{status:'completed',received_bytes:100,result_ids:['saved-record']});await e.poll()
  e.uploads[0].progress(55);e.server.clear();e.uploads[0].lose();await settle();await e.poll()
  assert.equal(e.view(key).status,'completed');assert.equal(e.view(key).uploaded_bytes,100)
  assert.deepEqual(e.view(key).task.result_ids,['saved-record'])
})

test('duplicate cancellation stays pending until the server confirms it and drops unconfirmed bytes',async t=>{
  const e=fixture(t,{holdDelete:true,disconnectFails:true}),key=e.manager.enqueue(input());await settle();e.uploads[0].progress(55)
  const first=e.manager.cancel(key),second=e.manager.cancel(key);await settle()
  assert.equal(e.deleteCount(),1);assert.equal(e.view(key).status,'cancelling');assert.equal(e.view(key).uploaded_bytes,0)
  assert.equal(e.uploads[0].active,true,'DELETE must reach the server before the upload is aborted')
  e.uploads[0].progress(99);assert.equal(e.view(key).uploaded_bytes,0,'cancelling must not show optimistic upload progress')
  e.resolveDelete(key);await first;await second
  assert.equal(e.uploads[0].active,false);assert.equal(e.view(key).status,'cancelled');assert.equal(e.task(key).status,'cancelled')
})

test('a rejected DELETE still aborts the upload and reports the resulting server failure without inventing cancellation',async t=>{
  const e=fixture(t,{holdDelete:true,disconnectFails:true}),key=e.manager.enqueue(input());await settle()
  const cancelled=e.manager.cancel(key);await settle();assert.equal(e.uploads[0].active,true)
  e.rejectDelete(key);await cancelled;await settle()
  assert.equal(e.uploads[0].active,false);assert.equal(e.view(key).status,'cancelling');assert(e.view(key).error)
  await e.poll();assert.equal(e.view(key).status,'failed');assert.equal(e.view(key).task.status,'failed')
  assert.deepEqual(e.view(key).task.result_ids,[])
})

test('DELETE timeout bounds the cancellation wait before aborting an unconfirmed upload',async t=>{
  const e=fixture(t,{holdDelete:true,disconnectFails:true}),key=e.manager.enqueue(input());await settle()
  const cancelled=e.manager.cancel(key);await settle();await e.clock.advance(14999)
  assert.equal(e.uploads[0].active,true);assert.equal(e.view(key).status,'cancelling')
  await e.clock.advance(1);await cancelled
  assert.equal(e.uploads[0].active,false);assert.equal(e.deleteCount(),1)
  await e.poll();assert.equal(e.view(key).status,'failed');assert.deepEqual(e.view(key).task.result_ids,[])
})

test('a DELETE acknowledgement that already reports failed is preserved honestly after upload teardown',async t=>{
  const e=fixture(t,{holdDelete:true,disconnectFails:true}),key=e.manager.enqueue(input());await settle()
  const cancelled=e.manager.cancel(key);await settle();assert.equal(e.uploads[0].active,true)
  e.resolveDelete(key,'failed');await cancelled
  assert.equal(e.uploads[0].active,false);assert.equal(e.view(key).status,'failed');assert.equal(e.view(key).task.status,'failed')
})

test('a server commit that wins cancellation preserves the completed record rather than deleting it',async t=>{
  const e=fixture(t,{commitWins:true}),key=e.manager.enqueue(input());await settle();await e.manager.cancel(key)
  assert.equal(e.view(key).status,'completed');assert.deepEqual(e.view(key).task.result_ids,['saved-record'])
})

test('lost POST response is reconciled by UUID without repeating the reservation',async t=>{
  const e=fixture(t,{losePost:true}),key=e.manager.enqueue(input());await settle()
  assert.equal(e.view(key).status,'checking');await e.poll()
  assert.equal(e.view(key).status,'uploading');assert.equal(e.postCount(),1);assert.equal(e.uploads.length,1)
})

test('lost accepted PUT response checks the original task without another upload',async t=>{
  const e=fixture(t),key=e.manager.enqueue(input());await settle()
  Object.assign(e.task(key),{status:'queued',received_bytes:100});e.uploads[0].lose();await settle()
  assert.equal(e.view(key).status,'queued');assert.equal(e.postCount(),1);assert.equal(e.uploads.length,1)
})

test('two upload slots snapshot metadata and continue when a page subscriber leaves',async t=>{
  const e=fixture(t),draft=input('first.jpg'),first=e.manager.enqueue(draft)
  draft.note='Changed after submit';e.manager.enqueue(input('second.jpg'));e.manager.enqueue(input('third.jpg'));await settle()
  assert.equal(e.uploads.length,2);assert.equal(JSON.parse(e.requests.find(request=>request.method==='POST').body).note,'Original observation')
  const unsubscribe=e.manager.subscribe(()=>{});unsubscribe();e.uploads[0].finish();await settle()
  assert.equal(e.uploads.length,3);assert.equal(e.uploads.filter(xhr=>xhr.active).length,2)
  assert.equal(e.view(first).status,'queued')
})

test('dispose blocks old-account callbacks, aborts uploads and cancels only the captured old-service tasks',async t=>{
  const e=fixture(t),snapshots=[];e.manager.subscribe(snapshot=>snapshots.push(snapshot))
  e.manager.enqueue(input());await settle();const count=snapshots.length
  e.setCurrent(false);e.uploads[0].progress(99);e.manager.dispose();await settle();await e.clock.advance(2000000)
  assert.equal(snapshots.length,count);assert.deepEqual(e.manager.getSnapshot(),[]);assert(e.deleteCount()>0)
  assert(e.requests.every(request=>request.url.startsWith('https://service-a.invalid/agriscan/api/')&&request.headers.Authorization==='Bearer SyntheticSessionA'))
})

test('dispose also cancels a server reservation whose POST response has not arrived',async t=>{
  const e=fixture(t,{holdPost:true}),key=e.manager.enqueue(input());await settle()
  e.setCurrent(false);e.manager.dispose();await settle()
  assert.equal(e.task(key).status,'cancelled');assert.deepEqual(e.manager.getSnapshot(),[]);assert.equal(e.postCount(),1)
})

test('a missing previously known server task fails explicitly without a new reservation',async t=>{
  const e=fixture(t),key=e.manager.enqueue(input());await settle();e.uploads[0].finish();await settle();e.server.clear();await e.poll()
  assert.equal(e.view(key).status,'failed');assert.match(e.view(key).error,/任务已失效/);assert.equal(e.postCount(),1)
})

test('empty File.type has the same nonempty MIME fallback for reservation and upload',async t=>{
  const e=fixture(t);e.manager.enqueue({file:file('unknown.jpg',''),kind:'image'});await settle()
  assert.equal(JSON.parse(e.requests.find(request=>request.method==='POST').body).content_type,'application/octet-stream')
  assert.equal(e.uploads[0].headers['Content-Type'],'application/octet-stream')
})
