const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const req=createRequire(path.resolve('frontend/package.json')),ts=req('typescript');
const text=fs.readFileSync('frontend/src/Pages.tsx','utf8');
const tree=ts.createSourceFile('Pages.tsx',text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const component=tree.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='DetectPage');
function named(body,name){for(const node of body.statements){if(ts.isFunctionDeclaration(node)&&node.name?.text===name)return node;if(ts.isVariableStatement(node)&&node.declarationList.declarations.some(value=>value.name.getText()===name))return node}throw Error(name)}
function compile(node,scope,name){const js=ts.transpileModule(node.getText(),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None}}).outputText;return new Function(...Object.keys(scope),js+';return '+name)(...Object.values(scope))}
const saved={id:'fixture-A',name:'leaf.jpg',crop:'苹果',status:'attention',result:'苹果黑星病',confidence:.846,plot_name:'',created_at:'2026-10-29T00:00:00Z',image_url:null,is_demo:false,note:'',candidates:[],boxes:[],prediction_model:{name:'Fixture detector',task:'detect',onnx_sha256:'a'.repeat(64)}};
function environment(){
  const box={token:'A',events:[],requests:[],selected:'previous-result',file:new File(['leaf'],'leaf.jpg',{type:'image/jpeg'})};
  const scope={file:box.file,fileOverLimit:false,imageMax:10,modelReady:true,crop:'番茄',plotId:'',note:'',client:{features:{image_detection:true,plots:true,assistant:true}},mounted:{current:true},completedUpload:{current:false},acceptedToken:{current:null},previewKey:{current:null},input:{current:{value:'old-selected-file',click(){box.events.push(['picker-click',this.value])}}},getToken:()=>box.token,requireAuth:()=>box.token==='A'};
  for(const name of ['setDragging','toast','setSubmitError'])scope[name]=(...args)=>box.events.push([name,...args]);scope.setFile=value=>{box.file=value;box.events.push(['setFile',value])};
  scope.tasks={manager:{enqueue(input){if(box.reject)throw Error('queue unavailable');box.requests.push(input);return 'task-'+box.requests.length}},select(key){box.selected=key;box.events.push(['select',key])}};
  for(const name of ['submit','chooseFile','openPicker'])box[name]=compile(named(component.body,name),scope,name);box.scope=scope;return box;
}
const cases=[];
(async()=>{
  {
    const b=environment();b.submit({preventDefault(){}});b.submit({preventDefault(){}});assert.equal(b.requests.length,1);assert.equal(b.scope.completedUpload.current,true);assert.equal(b.selected,'task-1');
    cases.push('submit snapshots one task synchronously and duplicate clicks cannot enqueue twice');
    b.selected='completed-task';b.events=[];b.openPicker();assert.deepEqual(b.events,[['picker-click','']]);b.events=[];b.chooseFile(undefined);assert.equal(b.selected,'completed-task');assert.equal(b.events.length,0);b.chooseFile(new File(['wrong'],'wrong.txt',{type:'text/plain'}));assert.equal(b.selected,'completed-task');assert.equal(b.scope.completedUpload.current,true);
    b.events=[];b.chooseFile(b.file);assert.equal(b.selected,null);assert.equal(b.scope.completedUpload.current,false);assert(b.events.some(row=>row[0]==='setFile'));cases.push('picker cancellation or invalid file keeps the previous task/result; a valid same-file selection starts a fresh editable input without cancelling other tasks');
  }
  {
    const b=environment();b.reject=true;b.submit({preventDefault(){}});assert.equal(b.requests.length,0);assert.equal(b.scope.completedUpload.current,false);assert(b.events.some(row=>row[0]==='setSubmitError'));b.reject=false;b.submit({preventDefault(){}});assert.equal(b.requests.length,1);cases.push('an enqueue failure unlocks the existing input for an explicit retry');
    const other=environment();other.token='B';other.submit({preventDefault(){}});assert.equal(other.requests.length,0);cases.push('an expired account cannot enqueue a task through the old detection screen');
  }
  {
    const effect=component.body.statements.find(node=>ts.isExpressionStatement(node)&&ts.isCallExpression(node.expression)&&node.expression.expression.getText()==='useEffect'&&node.expression.arguments[0]?.getText().includes('const token=getToken(),key=tasks.selectedKey')).expression.arguments[0];
    for(const mode of ['new-account','unmounted','another-task','dialog','saved-only','visible']){
      let token='A';const calls=[],frames=[],mounted={current:true},viewedKey={current:'task-1'},scope={result:mode==='saved-only'?{...saved,status:'awaiting_model'}:saved,tasks:{selectedKey:'task-1'},getToken:()=>token,acceptedToken:{current:null},mounted,viewedKey,setCrop:()=>calls.push('crop'),requestAnimationFrame:fn=>{frames.push(fn);return 1},cancelAnimationFrame(){},resultHeading:{current:{focus:()=>calls.push('focus'),scrollIntoView:()=>calls.push('scroll')}},reducedMotion:()=>true,document:{querySelector:()=>mode==='dialog'?{}:null}};
      const js=ts.transpileModule('const effect='+effect.getText()+';',{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;new Function(...Object.keys(scope),js+';effect()')(...Object.values(scope));if(mode==='new-account')token='B';if(mode==='unmounted')mounted.current=false;if(mode==='another-task')viewedKey.current='task-2';frames[0]();
      if(['new-account','unmounted','another-task','dialog'].includes(mode))assert(!calls.includes('focus')&&!calls.includes('scroll'));else assert(calls.includes('focus'));if(mode==='saved-only')assert(!calls.includes('crop'));
    }
    cases.push('actual completion effect focuses only the currently viewed live session/task, preserves dialogs, and never claims crop inference for awaiting-model samples');
  }
  const assistantText=fs.readFileSync('frontend/src/FloatingAssistant.tsx','utf8'),assistantTree=ts.createSourceFile('Assistant.tsx',assistantText,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const assistant=assistantTree.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='FloatingAssistant');
  {
    const session={token:'A'},alive={current:true};const currentSession=compile(named(assistant.body,'currentSession'),{alive,getToken:()=>session.token,mountToken:{current:'A'}},'currentSession');
    const calls=[],cache={current:new Map()},scope={currentSession,features:{assistant:true},analysisCache:cache,analyzingRecord:{current:null},scrollMode:{current:null},alive:{current:true},openRef:{current:false},api:async()=>({conversation:{id:'discussion'},messages:[{id:1,content:'analysis'}]})};
    for(const name of ['setOpen','setHistory','setDetection','setFailedDetection','setActive','setMessages','setError','setBusy','setAnalyzing','setUnread','updateChat'])scope[name]=(...args)=>calls.push([name,...args]);
    const analyze=compile(named(assistant.body,'analyzeDetection'),scope,'analyzeDetection');await analyze(saved);assert(!calls.some(row=>row[0]==='setOpen'));assert.equal(cache.current.get(saved.id).detail.conversation.id,'discussion');
    const effect=assistant.body.statements.find(node=>ts.isExpressionStatement(node)&&ts.isCallExpression(node.expression)&&node.expression.expression.getText()==='useEffect'&&node.expression.arguments[0]?.getText().includes('analysisCache.current.get(adviceRequest.id)')).expression.arguments[0];
    const viewScope={...scope,handled:{current:new Set()},onDetectionHandled:()=>calls.push(['queue-consumed']),analyzeDetection:analyze,adviceRequest:saved,user:{username:'A'},loading:false,busy:false,onAdviceHandled:()=>calls.push(['handled']),api:()=>{throw Error('Explicit view must not request another POST')}};
    const viewJs=ts.transpileModule('const effect='+effect.getText()+';',{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
    const view=()=>new Function(...Object.keys(viewScope),viewJs+';effect()')(...Object.values(viewScope));view();assert(calls.some(row=>row[0]==='setOpen'&&row[1]===true));cases.push('automatic assistant analysis stays background; explicit view opens existing cached discussion without another request');
    calls.length=0;session.token='B';view();await analyze({...saved,id:'other'});assert.equal(calls.length,0);assert(!cache.current.has('other'));session.token='A';
    const deferred=[];scope.api=()=>new Promise(resolve=>deferred.push(resolve));
    const pendingAnalyze=compile(named(assistant.body,'analyzeDetection'),scope,'analyzeDetection');
    const pending=pendingAnalyze({...saved,id:'late'});calls.length=0;session.token='B';deferred[0]({conversation:{id:'late-chat'},messages:[]});await pending;
    assert.equal(calls.length,0);assert.equal(cache.current.get('late').detail,null);session.token='A';
    cases.push('exact session token change blocks explicit cached advice and late analysis callbacks without mutating messages or completion state');
    const missing={...saved,id:'feature-restored'};calls.length=0;viewScope.adviceRequest=missing;viewScope.analyzeDetection=pendingAnalyze;
    view();view();assert.equal(deferred.length,2);assert.equal(cache.current.get(missing.id).detail,null);assert.equal(scope.analyzingRecord.current,missing.id);assert(calls.some(row=>row[0]==='setOpen'&&row[1]===true));
    deferred[1]({conversation:{id:'restored-chat'},messages:[]});await new Promise(resolve=>setImmediate(resolve));view();assert.equal(deferred.length,2);assert.equal(cache.current.get(missing.id).detail.conversation.id,'restored-chat');
    cases.push('feature restored cache miss starts one analysis and repeated explicit views reuse its in-flight cache and final conversation');
    calls.length=0;viewScope.adviceRequest=saved;scope.analyzingRecord.current='queued-B';view();assert.equal(calls.length,0);scope.analyzingRecord.current=null;
    const appTree=ts.createSourceFile('App.tsx',fs.readFileSync('frontend/src/App.tsx','utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),app=appTree.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='App');
    const queueCalls=[];compile(named(app.body,'queueDetection'),{useCallback:fn=>fn,sessionToken:'A',getToken:()=>session.token,setAdviceRequest:value=>queueCalls.push(['advice',value]),setDetectionRequests:fn=>queueCalls.push(['queue',fn([])])},'queueDetection')({...saved,id:'queued-B'});
    assert.deepEqual(queueCalls,[['advice',null],['queue',[{...saved,id:'queued-B'}]]]);
    cases.push('same-render queued analysis ref blocks old cached advice despite stale busy=false; accepting a new detection clears older pending advice first');


  }
  const React=req('react'),{renderToStaticMarkup}=req('react-dom/server'),esbuild=req('esbuild');global.sessionStorage={getItem:()=>null};
  function load(entry){const output=esbuild.buildSync({entryPoints:[entry],bundle:true,write:false,platform:'node',format:'cjs',packages:'external',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env':JSON.stringify({VITE_APP_SURFACE:'web',VITE_API_PREFIX:'/agriscan'})}}).outputFiles[0].text;const mod={exports:{}};new Function('require','module','exports',output)(req,mod,mod.exports);return mod.exports.default}
  const Result=load('frontend/src/DetectResultView.tsx'),Journey=load('frontend/src/DetectionJourney.tsx');
  const props={record:saved,originalUrl:'blob:fixture',canChoose:true,canAsk:true,headingRef:{current:null},comparisonRef:{current:null},metadataRef:{current:null},onChooseNext(){},onViewAdvice(){}};
  const result=renderToStaticMarkup(React.createElement(Result,props));assert(result.includes('苹果检测完成')&&result.includes('再检测一张')&&result.includes('查看原图')&&result.includes('查看小禾建议'));assert(!result.includes('<form')&&!result.includes('crop-room')&&!result.includes('上传作物图片'));
  const pending=renderToStaticMarkup(React.createElement(Result,{...props,record:{...saved,status:'awaiting_model',result:null,confidence:null}}));assert(pending.includes('样本已保存')&&!pending.includes('检测完成'));cases.push('actual completed result DOM has no input form/theme room; awaiting state is only a saved sample');
  for(const [phase,label] of [['choose','选择照片'],['details','补充记录'],['detecting','检测中'],['complete','检测完成'],['saved','样本已保存'],['failed','检测未完成'],['cancelled','任务已取消'],['result_loading','读取结果']]){
    const html=renderToStaticMarkup(React.createElement(Journey,{phase,modelReady:true,canUpload:true,onUpload(){},onDetails(){},onResult(){}}));const current=html.match(/<button\b[^>]*aria-current="step"[\s\S]*?<\/button>/g)||[];assert.equal(current.length,1);assert(current[0].includes(label));
  }
  cases.push('actual progress DOM moves aria-current through choose, details, detecting and the correct completed/saved labels');
  const report={status:'passed',source:'actual TSX handlers with deferred responses and real React static rendering',cases,provider_network_called:false,browser_ui_tested:false};
  fs.writeFileSync('.runtime/dual-model-20261029/completed-result-checks.json',JSON.stringify(report,null,2));console.log(JSON.stringify({status:'passed',cases:cases.length,report:'.runtime/dual-model-20261029/completed-result-checks.json'}));
})().catch(error=>{console.error(error);process.exitCode=1});
