const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module'),req=createRequire(path.resolve('frontend/package.json'));
const output=req('esbuild').buildSync({entryPoints:['shared/detectionTasks.ts'],bundle:true,write:false,platform:'node',format:'cjs'}).outputFiles[0].text,mod={exports:{}};new Function('module','exports',output)(mod,mod.exports);const {DetectionTaskManager}=mod.exports;
const tick=()=>new Promise(resolve=>setImmediate(resolve)),cases=[];
function environment(flags={}){
 const requests=[],uploads=[],tasks=new Map();let valid=true,seq=0,live=0,maxLive=0;
 const response=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(body)});
 const fetcher=async(url,options={})=>{
  const method=options.method||'GET';requests.push({url,method,headers:options.headers,body:options.body});
  if(method==='POST'){
   const data=JSON.parse(options.body),task={...data,id:'task-'+(++seq),status:'awaiting_upload',received_bytes:0,total_bytes:data.size_bytes,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),error:null,result_ids:[]};tasks.set(task.id,task);
   if(flags.loseCreate)throw Error('response lost');if(flags.deferCreate)return await new Promise((resolve,reject)=>{flags.resolveCreate=()=>resolve(response(task,201));flags.rejectCreate=reject});return response(task,201);
  }
  if(method==='DELETE'){
   const task=tasks.get(url.split('/').pop());if(!task)return response({},404);
   task.status=flags.commitWins?'completed':flags.cancelling?'cancelling':'cancelled';task.result_ids=flags.commitWins?['saved-record']:[];return response(task);
  }
  if(url.endsWith('/detection-tasks')){if(flags.listOffline)throw Error('poll timeout');return response([...tasks.values()]);}
  if(flags.deferIndividual)return await new Promise(resolve=>flags.resolveIndividual=()=>resolve(response({},404)));
  const task=tasks.get(url.split('/').pop());return task?response(task):response({},404);
 };
 const xhrFactory=()=>{
  const xhr={upload:{},headers:{},active:false,open(method,url){this.url=url;this.method=method},setRequestHeader(key,value){this.headers[key]=value},send(file){this.file=file;this.active=true;live++;maxLive=Math.max(maxLive,live);uploads.push(this)},abort(){if(this.active){this.active=false;live--;this.onabort?.()}},finish(status='queued'){if(!this.active)return;this.active=false;live--;const id=this.url.split('/').at(-2),task=tasks.get(id);task.status=status;task.received_bytes=task.total_bytes;this.status=202;this.responseText=JSON.stringify(task);this.onload()},refuse(status){if(this.active){this.active=false;live--;this.status=status;this.getResponseHeader=()=> '0';this.onload()}},lose(){if(this.active){this.active=false;live--;this.onerror()}}};return xhr;
 };
 const manager=new DetectionTaskManager({apiBaseUrl:'https://service-a.invalid/agriscan/api',token:'token-A',isCurrent:()=>valid,fetcher,xhrFactory,pollIntervalMs:999999});
 return {manager,requests,uploads,tasks,flags,setValid:value=>valid=value,maxLive:()=>maxLive};
}
function input(name='leaf.jpg'){return {kind:'image',file:new File(['a'.repeat(100)],name,{type:'image/jpeg'}),note:'original note'}}
(async()=>{
 {
  const e=environment(),notifications=[];let unsubscribe=e.manager.subscribe(snapshot=>notifications.push(snapshot));const draft=input('first.jpg'),first=e.manager.enqueue(draft);draft.note='changed after click';e.manager.enqueue(input('second.jpg'));e.manager.enqueue(input('third.jpg'));await tick();
  assert.equal(e.uploads.length,2);assert.equal(e.requests.filter(r=>r.method==='POST').length,2);assert.equal(e.maxLive(),2);assert.equal(JSON.parse(e.requests[0].body).note,'original note');
  e.uploads[0].upload.onprogress({loaded:55});assert.equal(e.manager.getSnapshot().find(j=>j.key===first).uploaded_bytes,55);unsubscribe();e.uploads[0].finish();await tick();assert.equal(e.uploads.length,3);assert.equal(e.maxLive(),2);
  unsubscribe=e.manager.subscribe(snapshot=>notifications.push(snapshot));const task=e.manager.getSnapshot().find(j=>j.key===first).task;e.tasks.get(task.id).status='completed';e.tasks.get(task.id).result_ids=['result-first'];await e.manager.refresh();assert.equal(e.manager.getSnapshot().find(j=>j.key===first).status,'completed');
  e.uploads[1].finish();e.uploads[2].finish();await tick();assert.equal(e.manager.getSnapshot().find(j=>j.key===first).status,'completed');unsubscribe();e.manager.dispose();cases.push('two upload slots, real XHR progress and immutable input snapshot survive view unsubscribe/navigation and a third queued file');
 }
 {
  const e=environment({loseCreate:true}),key=e.manager.enqueue(input());await tick();assert.equal(e.manager.getSnapshot()[0].status,'checking');await e.manager.refresh();await tick();assert.equal(e.requests.filter(r=>r.method==='POST').length,1);assert.equal(e.uploads.length,1);assert.equal(e.manager.getSnapshot()[0].key,key);e.manager.dispose();cases.push('lost create response recovers the same client UUID through GET without another POST');
 }
 {
  const e=environment();e.manager.enqueue(input());await tick();const xhr=e.uploads[0],task=[...e.tasks.values()][0];task.status='queued';xhr.lose();await tick();assert.equal(e.manager.getSnapshot()[0].status,'queued');assert.equal(e.requests.filter(r=>r.method==='POST').length,1);assert.equal(e.uploads.length,1);e.manager.dispose();cases.push('lost accepted upload response checks the original server task without reuploading or recreating');
 }
 {
  const e=environment({cancelling:true}),key=e.manager.enqueue(input());await tick();e.uploads[0].finish('processing');await tick();await Promise.all([e.manager.cancel(key),e.manager.cancel(key)]);assert.equal(e.requests.filter(r=>r.method==='DELETE').length,1);assert.equal(e.manager.getSnapshot()[0].status,'cancelling');[...e.tasks.values()][0].status='cancelled';await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].status,'cancelled');e.manager.dispose();cases.push('duplicate cancel calls share one request and cancelling remains pending until the server confirms cancelled');
 }
 {
  const e=environment({commitWins:true}),key=e.manager.enqueue(input());await tick();await e.manager.cancel(key);assert.equal(e.manager.getSnapshot()[0].status,'completed');assert.deepEqual(e.manager.getSnapshot()[0].task.result_ids,['saved-record']);e.manager.dispose();cases.push('a completed server commit wins cancellation and its stored result IDs are retained');
 }
 {
  const e=environment();e.manager.enqueue(input());await tick();e.uploads[0].finish();await tick();e.tasks.clear();await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].status,'failed');assert(e.manager.getSnapshot()[0].error.includes('服务已重启'));assert.equal(e.requests.filter(r=>r.method==='POST').length,1);e.manager.dispose();cases.push('server task disappearance becomes explicit failure without a duplicate reservation');
 }
 {
  const e=environment(),snapshots=[];e.manager.subscribe(value=>snapshots.push(value));e.manager.enqueue(input());await tick();const previous=snapshots.length;e.setValid(false);e.uploads[0].upload.onprogress({loaded:99});assert.equal(snapshots.length,previous);e.manager.dispose();await tick();assert.equal(e.manager.getSnapshot().length,0);assert(e.requests.filter(r=>r.method==='DELETE').length);assert(e.requests.every(r=>r.url.startsWith('https://service-a.invalid/agriscan/api/')&&r.headers.Authorization==='Bearer token-A'));assert.equal(snapshots.length,previous);cases.push('changed account stops callbacks, aborts files and cancels only captured old-service tasks with the captured old token');
 }

 {
  const e=environment();e.manager.enqueue({kind:'image',file:new File(['content'],'no-mime.jpg')});await tick();assert.equal(JSON.parse(e.requests.find(r=>r.method==='POST').body).content_type,'application/octet-stream');assert.equal(e.uploads[0].headers['Content-Type'],'application/octet-stream');e.manager.dispose();cases.push('empty browser File.type uses the same nonempty MIME fallback in reservation and raw upload');
 }

 {
  const e=environment(),draft=input();e.manager.enqueue(draft);await tick();e.uploads[0].refuse(429);await tick();assert.equal(e.manager.getSnapshot()[0].status,'awaiting_upload');await new Promise(resolve=>setTimeout(resolve,1050));await e.manager.refresh();await tick();assert.equal(e.uploads.length,2);assert.equal(e.uploads[1].file,draft.file);assert.equal(e.requests.filter(r=>r.method==='POST').length,1);e.manager.dispose();cases.push('explicit upload 429 retains the original file and retries only PUT on the same reserved task after bounded backoff');
 }
 {
  const e=environment({deferIndividual:true});e.manager.enqueue(input());await tick();const task=[...e.tasks.values()][0];e.tasks.clear();const refresh=e.manager.refresh();await tick();e.tasks.set(task.id,task);task.result_ids=['saved-record'];e.uploads[0].finish('completed');await tick();assert.equal(e.manager.getSnapshot()[0].status,'completed');e.flags.resolveIndividual();await refresh;assert.equal(e.manager.getSnapshot()[0].status,'completed');assert.deepEqual(e.manager.getSnapshot()[0].task.result_ids,['saved-record']);e.manager.dispose();cases.push('late GET 404 cannot downgrade an already confirmed completed upload or discard its stored result IDs');
 }

 {
  const e=environment(),key=e.manager.enqueue(input());await tick();const task=[...e.tasks.values()][0];task.status='completed';task.result_ids=['saved-record'];await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].status,'completed');e.tasks.clear();e.uploads[0].lose();await tick();assert.equal(e.manager.getSnapshot()[0].status,'completed');assert.deepEqual(e.manager.getSnapshot()[0].task.result_ids,['saved-record']);await e.manager.cancel(key);assert.equal(e.manager.getSnapshot()[0].status,'completed');e.manager.dispose();cases.push('GET-confirmed completion survives a late XHR error and unavailable status lookup without reentering checking');
 }

 {
  const e=environment({deferCreate:true}),snapshots=[];e.manager.subscribe(value=>snapshots.push(value));e.manager.enqueue(input());await tick();const count=snapshots.length;e.setValid(false);e.manager.dispose();e.flags.resolveCreate();await tick();assert.equal(snapshots.length,count);assert.equal(e.manager.getSnapshot().length,0);assert.equal([...e.tasks.values()][0].status,'cancelled');assert(e.requests.filter(r=>r.method==='DELETE').every(r=>r.headers.Authorization==='Bearer token-A'));assert.equal(e.requests.filter(r=>r.method==='POST').length,1);cases.push('late reservation after disposal is cancelled with the old session token and cannot publish into a new account');
 }
 fs.writeFileSync('.runtime/detection-tasks-20261029/core-checks.json',JSON.stringify({status:'passed',source:'actual shared DetectionTaskManager with deferred HTTP/XHR events',cases,production_network_called:false},null,2));console.log(JSON.stringify({status:'passed',cases:cases.length}));
})().catch(error=>{console.error(error);process.exitCode=1});
