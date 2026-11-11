const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module'),req=createRequire(path.resolve('mobile/package.json')),ts=req('typescript'),cases=[];
function tree(file){return ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX)}
const common=tree('mobile/src/accountSecurity.ts');
const fn=(root,name)=>root.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text===name);
function compile(node,bindings,name){const js=ts.transpileModule(node.getText().replace(/^export\s+(default\s+)?/,''),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None}}).outputText;return new Function(...Object.keys(bindings),js+';return '+name)(...Object.values(bindings))}
const validEmail=compile(fn(common,'validEmail'),{},'validEmail'),resetError=compile(fn(common,'resetError'),{validEmail},'resetError');
function session(requireLogin=false){
 const state={base:'https://fixture.example.test/agriscan',token:requireLogin?'session-A':null,route:requireLogin?'#settings':'#forgot-password'},effects=[],states=[],refs=[],listeners=new Map();let si=0,ri=0;
 const window={location:{get hash(){return state.route}},addEventListener:(name,cb)=>listeners.set(name,cb),removeEventListener:name=>listeners.delete(name),setInterval:()=>1,clearInterval(){}};
 const bindings={getServiceBase:()=>state.base,getToken:()=>state.token,window,useRef:value=>refs[ri++]??(refs[ri-1]={current:value}),useState:value=>{const index=si++;if(!(index in states))states[index]=value;return[states[index],next=>states[index]=typeof next==='function'?next(states[index]):next]},useEffect:effect=>effects.push(effect)};
 const hook=compile(fn(common,'useAccountScope'),bindings,'useAccountScope'),scope=hook(requireLogin),cleanup=effects.map(effect=>effect()).filter(Boolean);
 return {state,scope,bindings,states,refs,cleanup:()=>cleanup.forEach(effect=>effect()),emit:name=>listeners.get(name)?.(),renderCooldown(){si=0;ri=0;return compile(fn(common,'useMailCooldown'),bindings,'useMailCooldown')()}};
}
function environment(component){
 const runtime=session(component==='EmailBinding'),events=[],requests=[],fields={code:'123456',new_password:'REDACTED_SECRET',confirm:'SyntheticNewPassword42',current_password:'REDACTED_SECRET'};
 const values={enabled:true,loading:false,complete:false,email:'owner@example.test',scope:runtime.scope,cooldown:{seconds:0,start:()=>events.push(['cooldown'])},form:{current:{reset:()=>events.push(['reset'])}},validEmail,resetError,FormData:class{get(key){return fields[key]}},api:(url,options)=>new Promise((resolve,reject)=>requests.push({url,body:JSON.parse(options.body),signal:options.signal,resolve,reject}))};
 for(const name of ['setBusy','setError','setMessage','setEmail','setShow','setComplete','setStatus'])values[name]=value=>events.push([name,value]);
 const decl=fn(tree('mobile/src/'+component+'.tsx'),component),child=name=>decl.body.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text===name);
 return {...runtime,events,requests,fields,send:compile(child('sendCode'),values,'sendCode'),submit:()=>compile(child('submit'),values,'submit')({preventDefault(){},currentTarget:{}})};
}
(async()=>{
 assert.equal(resetError('bad','123456','1234567890','1234567890'),'请填写有效的邮箱地址。');assert(resetError('ok@example.test','12345','1234567890','1234567890'));assert(resetError('ok@example.test','123456','123456789','123456789'));assert(resetError('ok@example.test','123456','x'.repeat(129),'x'.repeat(129)));assert.equal(resetError('ok@example.test','123456','1234567890','1234567890'),'');cases.push('actual reset validator rejects malformed email/code and password bounds before any request');
 {
  const e=session(true),first=e.scope.begin();assert(first);assert.equal(e.scope.begin(),null);e.scope.finish(first);assert(e.scope.begin());e.cleanup();cases.push('actual account scope synchronously locks code and verify requests and aborts on cleanup');
 }
 for(const mode of ['route','token','service','unmount']){
  const e=session(true),pending=e.scope.begin();if(mode==='route')e.state.route='#home';if(mode==='token')e.state.token='session-B';if(mode==='service')e.state.base='https://different.example.test';if(mode==='unmount')e.cleanup();else e.emit(mode==='route'?'hashchange':mode==='token'?'storage':'agriscan-mobile-service-changed');assert.equal(e.scope.current(),false);assert(pending.signal.aborted);if(mode!=='unmount')e.cleanup();
 }
 cases.push('actual route/token/service/unmount invalidation aborts requests and rejects late account writes');
 {
  const e=session(),cooldown=e.renderCooldown(),now=Date.now();cooldown.start();const next=e.renderCooldown();assert(next.seconds>=59&&next.seconds<=60);assert(e.states[0]>=now+60000);e.cleanup();cases.push('actual cooldown retains an absolute sixty-second deadline independent of email input');
 }
 {
  const e=environment('PasswordReset');e.fields.confirm='different';await e.submit();assert.equal(e.requests.length,0);assert(e.events.some(row=>row[0]==='setError'));e.cleanup();cases.push('actual reset handler refuses mismatched confirmation without a POST');
 }
 {
  const e=environment('PasswordReset'),a=e.send(),b=e.send();assert.equal(e.requests.length,1);e.requests[0].resolve({message:'fixture must not be displayed'});await a;await b;assert(e.events.some(row=>row[0]==='setMessage'&&row[1].startsWith('如果该邮箱')));assert(!JSON.stringify(e.events).includes('fixture must'));e.cleanup();cases.push('duplicate send clicks POST once and use fixed non-enumerating feedback');
 }
 {
  const e=environment('PasswordReset'),pending=e.submit();e.requests[0].reject(Error('provider echoed '+e.fields.new_password+' '+e.fields.code));await pending;assert(!JSON.stringify(e.events).includes(e.fields.new_password));assert(!JSON.stringify(e.events).includes(e.fields.code));e.cleanup();cases.push('actual reset errors never echo provider password or OTP details');
 }
 for(const component of ['PasswordReset','EmailBinding']){
  const e=environment(component),pending=e.submit(),count=e.events.length;e.state.route='#home';e.requests[0].resolve({email:'new@example.test',verified:true});await pending;assert.equal(e.events.length,count);e.cleanup();
 }
 cases.push('late reset and binding success after route change cannot mutate the next page');
 {
  const e=environment('EmailBinding'),pending=e.submit(),count=e.events.length;assert.equal(e.requests[0].body.current_password,e.fields.current_password);e.state.token='session-B';e.requests[0].resolve({email:'new@example.test',verified:true});await pending;assert.equal(e.events.length,count);e.cleanup();cases.push('binding sends current-password proof and cannot write status after account replacement');
 }
 {
  const e=environment('EmailBinding'),pending=e.submit();e.requests[0].resolve({email:'new@example.test',verified:true});await pending;assert(e.events.some(row=>row[0]==='setStatus'&&row[1].verified));assert(e.events.some(row=>row[0]==='reset'));e.cleanup();cases.push('verified binding updates only the current form and clears password/code proof inputs');
 }
 fs.writeFileSync('.runtime/mobile-auth-qa-20261029/form-checks.json',JSON.stringify({status:'passed',source:'actual mobile TSX handlers and scope/cooldown hook',cases,production_network_called:false,smtp_mail_sent:false,real_credential_changed:false},null,2));console.log(JSON.stringify({status:'passed',cases:cases.length}));
})().catch(error=>{console.error(error);process.exitCode=1});
