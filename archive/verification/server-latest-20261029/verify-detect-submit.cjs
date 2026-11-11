// Execute the actual TSX submit handler with deferred API responses; no DOM/network.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const ts=require(path.resolve('frontend/node_modules/typescript'));
const source=fs.readFileSync('frontend/src/Pages.tsx','utf8');
const tree=ts.createSourceFile('Pages.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const component=tree.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='DetectPage');
const handler=component.body.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='submit');
assert(handler,'The real DetectPage submit handler must exist.');
const compiled=ts.transpileModule(handler.getText(tree),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None}}).outputText;
const saved={id:'owned-A-record',crop:'苹果',status:'attention'};
function environment(){
  const box={token:'token-A',events:[],requests:[],mounted:{current:true},pendingUpload:{current:null}};
  const state={busy:false,file:new Blob(['leaf'],{type:'image/jpeg'}),fileOverLimit:false,modelReady:true,crop:'番茄',plotId:'',note:'',
    client:{features:{image_detection:true,plots:true,assistant:true}},mounted:box.mounted,pendingUpload:box.pendingUpload,
    getToken:()=>box.token,requireAuth:()=>true,
    api:(_route,options)=>new Promise((resolve,reject)=>box.requests.push({resolve,reject,options}))};
  for(const name of ['setBusy','setDragging','setResult','setCrop','onChange','onDetected','toast'])state[name]=(...args)=>box.events.push({name,args});
  const create=new Function(...Object.keys(state),compiled+'; return submit;');
  box.submit=create(...Object.values(state));
  box.start=()=>{const promise=box.submit({preventDefault(){}});box.events.length=0;return promise};
  return box;
}
(async()=>{
  const cases=[];
  {
    const box=environment(),run=box.start();box.requests[0].resolve(saved);await run;
    assert.deepEqual(box.events.map(event=>event.name),['setCrop','setResult','onChange','onDetected','toast','setBusy']);
    assert.equal(box.events[0].args[0],'苹果');assert.equal(box.events.at(-1).args[0],false);
    cases.push('current session keeps automatic crop, saved result, callbacks and success feedback');
  }
  {
    const box=environment(),run=box.start();box.token='token-B';box.requests[0].resolve(saved);await run;
    assert.deepEqual(box.events,[]);cases.push('late A success after B login causes no crop/state/callback/toast changes');
  }
  {
    const box=environment(),run=box.start();box.mounted.current=false;box.pendingUpload.current.abort();box.pendingUpload.current=null;
    assert.equal(box.requests[0].options.signal.aborted,true);box.requests[0].resolve(saved);await run;
    assert.deepEqual(box.events,[]);cases.push('unmount aborts request and ignores even an abort-insensitive deferred success');
  }
  {
    const box=environment(),run=box.start();box.token='token-B';box.requests[0].reject(new Error('A-only failure'));await run;
    assert.deepEqual(box.events,[]);cases.push('late A failure does not toast or change busy state for B');
  }
  {
    const box=environment(),run=box.start();box.requests[0].reject(new Error('current failure'));await run;
    assert.deepEqual(box.events.map(event=>event.name),['toast','setBusy']);
    cases.push('current session failure remains visible and releases busy state');
  }
  {
    const box=environment(),first=box.start(),second=box.start();
    assert.equal(box.requests[0].options.signal.aborted,true);box.requests[0].resolve(saved);await first;
    assert.deepEqual(box.events,[]);box.requests[1].resolve(saved);await second;
    assert.equal(box.events.filter(event=>event.name==='onDetected').length,1);
    cases.push('superseded response cannot overwrite the active upload');
  }
  const report={status:'passed',source:'Actual TSX DetectPage.submit AST transpiled in memory',network_called:false,dom_tested:false,cases};
  fs.writeFileSync('.runtime/server-latest-20261029/detect-deferred-checks.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify({status:'passed',cases:cases.length,report:'.runtime/server-latest-20261029/detect-deferred-checks.json'}));
})().catch(error=>{console.error(error);process.exitCode=1});
