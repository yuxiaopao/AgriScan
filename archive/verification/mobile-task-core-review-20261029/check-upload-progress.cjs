const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {createRequire}=require('node:module'),req=createRequire(path.resolve('frontend/package.json'));
const source=fs.readFileSync('shared/detectionTasks.ts'),compiled=req('esbuild').buildSync({entryPoints:['shared/detectionTasks.ts'],bundle:true,write:false,platform:'node',format:'cjs'}).outputFiles[0].text;
const mod={exports:{}};new Function('module','exports',compiled)(mod,mod.exports);const {DetectionTaskManager}=mod.exports;
const tick=()=>new Promise(resolve=>setImmediate(resolve)),cases=[];
function fixture(){
 let server=null,listFails=false,posts=0;const uploads=[];
 const response=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(body)});
 const fetcher=async(url,options={})=>{
  if(options.method==='POST'){posts++;const body=JSON.parse(options.body);server={id:'synthetic-task',client_request_id:body.client_request_id,filename:body.filename,kind:'image',status:'awaiting_upload',received_bytes:0,total_bytes:100,created_at:'2026-10-29T00:00:00',updated_at:'2026-10-29T00:00:00',error:null,result_ids:[]};return response(server,201)}
  if(options.method==='DELETE'){server.status='cancelling';server.received_bytes=0;return response(server)}
  if(url.endsWith('/detection-tasks')){if(listFails)throw Error('Synthetic transient poll failure');return response([server])}
  return response(server);
 };
 const xhrFactory=()=>{const xhr={upload:{},status:0,responseText:'',open(){},setRequestHeader(){},send(){uploads.push(this)},getResponseHeader(){return '5'},abort(){this.onabort?.()},progress(bytes){this.upload.onprogress({loaded:bytes})},lose(){this.onerror()},reply(status=202){this.status=status;this.responseText=JSON.stringify(server);this.onload()}};return xhr};
 const manager=new DetectionTaskManager({apiBaseUrl:'https://synthetic.invalid/agriscan/api',token:'SyntheticToken',isCurrent:()=>true,fetcher,xhrFactory,pollIntervalMs:999999});
 const key=manager.enqueue({file:new File(['x'.repeat(100)],'synthetic.jpg',{type:'image/jpeg'}),kind:'image'});
 return {manager,key,uploads,server:()=>server,view:()=>manager.getSnapshot()[0],posts:()=>posts,failList:()=>{listFails=true}};
}
async function check(name,action){const env=fixture();try{await tick();await action(env);cases.push({name,status:'passed'})}catch(error){cases.push({name,status:'failed',assertion:error.message})}finally{env.manager.dispose();await tick()}}
(async()=>{
 await check('active XHR remains uploading with real local byte progress when buffered server still reports awaiting_upload',async e=>{e.uploads[0].progress(55);assert.equal(e.view().status,'uploading');await e.manager.refresh();assert.equal(e.view().status,'uploading');assert.equal(e.view().uploaded_bytes,55);assert.equal(e.view().task.status,'awaiting_upload');assert.equal(e.posts(),1)});
 await check('active upload survives a transient poll error without a duplicate reservation',async e=>{e.uploads[0].progress(55);e.failList();await e.manager.refresh();assert.equal(e.view().status,'uploading');assert.equal(e.view().uploaded_bytes,55);assert.equal(e.posts(),1)});
 await check('server processing wins the local upload presentation while the XHR response is pending',async e=>{e.uploads[0].progress(55);Object.assign(e.server(),{status:'processing',received_bytes:100});await e.manager.refresh();assert.equal(e.view().status,'processing');assert.equal(e.view().uploaded_bytes,100)});
 await check('failed XHR uses the confirmed server bytes while checking instead of retaining optimistic bytes',async e=>{e.uploads[0].progress(55);Object.assign(e.server(),{status:'uploading',received_bytes:20});e.uploads[0].lose();await tick();assert.equal(e.view().status,'checking');assert.equal(e.view().uploaded_bytes,20);assert.equal(e.posts(),1)});
 await check('explicit 429 backoff resets progress to confirmed server bytes and keeps the original reservation',async e=>{e.uploads[0].progress(55);e.uploads[0].reply(429);await tick();assert.equal(e.view().status,'awaiting_upload');assert.equal(e.view().uploaded_bytes,0);assert.equal(e.posts(),1)});
 await check('confirmed cancellation is never masked by local upload state or stale local progress',async e=>{e.uploads[0].progress(55);await e.manager.cancel(e.key);assert.equal(e.view().status,'cancelling');assert.equal(e.view().uploaded_bytes,0);assert.equal(e.posts(),1)});
 await check('confirmed terminal completion and saved IDs survive a late XHR failure',async e=>{e.uploads[0].progress(55);Object.assign(e.server(),{status:'completed',received_bytes:100,result_ids:['synthetic-result']});await e.manager.refresh();e.uploads[0].lose();await tick();assert.equal(e.view().status,'completed');assert.equal(e.view().uploaded_bytes,100);assert.deepEqual(e.view().task.result_ids,['synthetic-result']);assert.equal(e.posts(),1)});
 await check('late local progress cannot replace server-confirmed processing bytes',async e=>{Object.assign(e.server(),{status:'processing',received_bytes:100});await e.manager.refresh();e.uploads[0].progress(55);assert.equal(e.view().status,'processing');assert.equal(e.view().uploaded_bytes,100)});
 await check('late local progress cannot downgrade completed bytes or saved result IDs',async e=>{Object.assign(e.server(),{status:'completed',received_bytes:100,result_ids:['synthetic-result']});await e.manager.refresh();e.uploads[0].progress(55);assert.equal(e.view().status,'completed');assert.equal(e.view().uploaded_bytes,100);assert.deepEqual(e.view().task.result_ids,['synthetic-result'])});
 const expectedRed=process.argv.includes('--expect-red'),failed=cases.filter(row=>row.status==='failed');
 const report={status:failed.length?'failed':'passed',expected_red:expectedRed,source:'actual shared DetectionTaskManager with independent synthetic HTTP/XHR event harness',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),cases,production_network_called:false};
 fs.writeFileSync('.runtime/mobile-task-core-review-20261029/'+(expectedRed?'core-red.json':'core-progress-checks.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({status:report.status,expected_red:expectedRed,cases:cases.length,failed:failed.map(row=>({name:row.name,assertion:row.assertion}))}));
 if(expectedRed?!failed.length:failed.length)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1});
