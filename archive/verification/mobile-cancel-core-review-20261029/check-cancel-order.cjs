const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {createRequire}=require('node:module'),req=createRequire(path.resolve('frontend/package.json'));
const source=fs.readFileSync('shared/detectionTasks.ts'),js=req('esbuild').buildSync({entryPoints:['shared/detectionTasks.ts'],bundle:true,write:false,platform:'node',format:'cjs'}).outputFiles[0].text;
const tick=()=>new Promise(resolve=>setImmediate(resolve)),cases=[];
function fixture(){
 const timers=new Map(),events=[],uploads=[],pending=[];let timerID=0,server=null,posts=0,deletes=0,hold=true;
 const timeout=(callback,ms)=>{const id=++timerID;timers.set(id,{callback,ms});return id},clear=id=>timers.delete(id);
 const mod={exports:{}};new Function('module','exports','setTimeout','clearTimeout',js)(mod,mod.exports,timeout,clear);
 const response=body=>({ok:true,status:200,json:async()=>structuredClone(body)});
 const fetcher=async(url,init={})=>{
  if(init.method==='POST'){posts++;const body=JSON.parse(init.body);server={id:'synthetic-task',client_request_id:body.client_request_id,kind:'image',filename:body.filename,status:'awaiting_upload',received_bytes:0,total_bytes:100,created_at:'2026-10-29',updated_at:'2026-10-29',error:null,result_ids:[]};return response(server)}
  if(init.method==='DELETE'){
   deletes++;events.push('DELETE_START');
   if(!hold){server.status='cancelled';return response(server)}
   return new Promise((resolve,reject)=>{
    const abort=()=>{events.push('DELETE_TIMEOUT');reject(new DOMException('Synthetic timeout','AbortError'))};init.signal.addEventListener('abort',abort,{once:true});
    pending.push({resolve(status){init.signal.removeEventListener('abort',abort);server.status=status;if(status==='completed')server.result_ids=['saved-result'];events.push('DELETE_ACK_'+status);resolve(response(server))},reject(){init.signal.removeEventListener('abort',abort);events.push('DELETE_REJECT');reject(Error('Synthetic unreachable cancellation'))}});
   });
  }
  return response(url.endsWith('/detection-tasks')?[server]:server);
 };
 const xhrFactory=()=>({upload:{},active:false,open(){},setRequestHeader(){},send(){this.active=true;uploads.push(this)},abort(){if(this.active){events.push('XHR_ABORT');this.active=false;if(!['cancelled','completed','failed'].includes(server.status))server.status='failed';this.onabort?.()}}});
 const manager=new mod.exports.DetectionTaskManager({apiBaseUrl:'https://synthetic.invalid/agriscan/api',token:'SyntheticToken',isCurrent:()=>true,fetcher,xhrFactory,pollIntervalMs:999999});
 const key=manager.enqueue({kind:'image',file:new File(['x'.repeat(100)],'synthetic.jpg',{type:'image/jpeg'})});
 return {manager,key,events,uploads,pending,timers,view:()=>manager.getSnapshot()[0],posts:()=>posts,deletes:()=>deletes,
  timeoutDelete(){const found=[...timers].find(([,entry])=>entry.ms===15000);assert(found);timers.delete(found[0]);found[1].callback()},
  async cleanup(){hold=false;manager.dispose();await tick();assert.equal(uploads.filter(xhr=>xhr.active).length,0);assert.equal(timers.size,0)}};
}
async function check(name,action){const e=fixture();try{await tick();await action(e);cases.push({name,status:'passed'})}catch(error){cases.push({name,status:'failed',assertion:error.message})}finally{await e.cleanup()}}
(async()=>{
 await check('pending server cancellation keeps XHR alive and duplicate clicks share one DELETE; ACK cancelled precedes abort',async e=>{const a=e.manager.cancel(e.key),b=e.manager.cancel(e.key);await tick();assert.equal(e.view().status,'cancelling');assert(e.uploads[0].active);assert.equal(e.deletes(),1);assert(!e.events.includes('XHR_ABORT'));e.pending[0].resolve('cancelled');await a;await b;assert.equal(e.view().status,'cancelled');assert(e.events.indexOf('DELETE_ACK_cancelled')<e.events.indexOf('XHR_ABORT'));assert.equal(e.posts(),1)});
 await check('DELETE rejection aborts the upload but does not invent a confirmed cancelled or failed state',async e=>{const a=e.manager.cancel(e.key);await tick();assert(e.uploads[0].active);e.pending[0].reject();await a;assert(!e.uploads[0].active);assert.equal(e.view().status,'cancelling');assert(e.view().error);assert(e.events.indexOf('DELETE_REJECT')<e.events.indexOf('XHR_ABORT'));await e.manager.refresh();assert.equal(e.view().status,'failed')});
 await check('existing fifteen-second cancellation request timeout eventually releases XHR without a fake terminal state',async e=>{const a=e.manager.cancel(e.key);await tick();assert(e.uploads[0].active);e.timeoutDelete();await a;assert(!e.uploads[0].active);assert.equal(e.view().status,'cancelling');assert(e.view().error);assert(e.events.indexOf('DELETE_TIMEOUT')<e.events.indexOf('XHR_ABORT'))});
 await check('server-reported failed terminal remains failed rather than being relabelled cancelled',async e=>{const a=e.manager.cancel(e.key);await tick();e.pending[0].resolve('failed');await a;assert.equal(e.view().status,'failed');assert(e.events.indexOf('DELETE_ACK_failed')<e.events.indexOf('XHR_ABORT'))});
 await check('server commit winning cancellation retains completed status and saved IDs',async e=>{const a=e.manager.cancel(e.key);await tick();e.pending[0].resolve('completed');await a;assert.equal(e.view().status,'completed');assert.deepEqual(e.view().task.result_ids,['saved-result']);assert(e.events.indexOf('DELETE_ACK_completed')<e.events.indexOf('XHR_ABORT'))});
 const failed=cases.filter(row=>row.status!=='passed'),report={status:failed.length?'failed':'passed',source:'actual shared core, independent public API/XHR/Deferred DELETE ordering harness',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),cases,production_network_called:false};
 fs.writeFileSync('.runtime/mobile-cancel-core-review-20261029/cancel-order-checks.json',JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,cases:cases.length,failed}));if(failed.length)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1});
