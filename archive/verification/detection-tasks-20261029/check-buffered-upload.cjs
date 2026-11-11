const fs=require('node:fs'),assert=require('node:assert/strict');
const existing=fs.readFileSync('.runtime/detection-tasks-20261029/check-task-manager.cjs','utf8').split('(async()=>{')[0];
const {environment,input,tick}=new Function('require',existing+';return {environment,input,tick}')(require);
const outcomes=[];
async function check(name,run){console.log('checking: '+name);try{await run();outcomes.push({name,status:'passed'})}catch(reason){outcomes.push({name,status:'failed',message:reason.message})}}
(async()=>{
 await check('active browser upload survives awaiting_upload polls and temporary poll failure without a second POST',async()=>{
  const e=environment();try{
   e.manager.enqueue(input());await tick();e.uploads[0].upload.onprogress({loaded:55});await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].status,'uploading');assert.equal(e.manager.getSnapshot()[0].uploaded_bytes,55);
   e.uploads[0].upload.onprogress({loaded:100});await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].status,'uploading');assert.equal(e.manager.getSnapshot()[0].uploaded_bytes,100);
   e.flags.listOffline=true;await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].status,'uploading');assert.equal(e.manager.getSnapshot()[0].uploaded_bytes,100);assert(e.manager.getSnapshot()[0].error);e.flags.listOffline=false;await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].error,null);
   e.uploads[0].finish('queued');await tick();e.uploads[0].upload.onprogress({loaded:1});assert.equal(e.manager.getSnapshot()[0].status,'queued');assert.equal(e.manager.getSnapshot()[0].uploaded_bytes,100);
   const task=[...e.tasks.values()][0];task.status='processing';await e.manager.refresh();task.status='awaiting_upload';task.received_bytes=0;await e.manager.refresh();assert.equal(e.manager.getSnapshot()[0].status,'processing');assert.equal(e.manager.getSnapshot()[0].uploaded_bytes,100);
   task.status='completed';task.received_bytes=100;task.result_ids=['saved-result'];await e.manager.refresh();e.uploads[0].upload.onprogress({loaded:0});assert.equal(e.manager.getSnapshot()[0].status,'completed');assert.equal(e.manager.getSnapshot()[0].uploaded_bytes,100);
   assert.equal(e.requests.filter(row=>row.method==='POST').length,1);assert.equal(e.uploads.length,1);
  }finally{e.manager.dispose()}
 });
 await check('GET recovery before a lost POST response still uploads exactly once to the original task',async()=>{
  const e=environment({deferCreate:true});try{
   e.manager.enqueue(input());await tick();await e.manager.refresh();assert(e.manager.getSnapshot()[0].task);e.flags.rejectCreate(Error('reservation response timed out'));await tick();assert.equal(e.uploads.length,1);assert.equal(e.requests.filter(row=>row.method==='POST').length,1);assert.equal(e.manager.getSnapshot()[0].status,'uploading');
  }finally{e.manager.dispose()}
 });

 await check('GET-confirmed queued or processing reservation is tracked without a duplicate PUT after POST failure',async()=>{
  for(const status of ['queued','processing']){
   const e=environment({deferCreate:true});try{
    e.manager.enqueue(input());await tick();const task=[...e.tasks.values()][0];task.status=status;task.received_bytes=100;await e.manager.refresh();e.flags.rejectCreate(Error('lost reservation response'));await tick();assert.equal(e.uploads.length,0);assert.equal(e.manager.getSnapshot()[0].status,status);assert.equal(e.requests.filter(row=>row.method==='POST').length,1);
   }finally{e.manager.dispose()}
  }
 });
 await check('cancelling while reservation is pending takes priority over a recovered reservation and never starts PUT',async()=>{
  const e=environment({deferCreate:true});try{
   const key=e.manager.enqueue(input());await tick();await e.manager.cancel(key);await e.manager.refresh();e.flags.rejectCreate(Error('lost reservation response'));await tick();assert.equal(e.uploads.length,0);assert.equal(e.manager.getSnapshot()[0].status,'cancelled');assert.equal(e.requests.filter(row=>row.method==='POST').length,1);assert.equal(e.requests.filter(row=>row.method==='DELETE').length,1);
  }finally{e.manager.dispose()}
 });
 const result={status:outcomes.every(row=>row.status==='passed')?'passed':'failed',source:'actual shared task manager with deferred reservation and XHR, no provider/network calls',cases:outcomes};console.log(JSON.stringify(result));
 fs.writeFileSync('.runtime/detection-tasks-20261029/buffered-upload-checks.json',JSON.stringify(result,null,2));if(result.status!=='passed')process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1});
