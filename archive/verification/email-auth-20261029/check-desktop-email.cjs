const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module'),req=createRequire(path.resolve('frontend/package.json')),ts=req('typescript');
const source=fs.readFileSync('frontend/src/EmailForms.tsx','utf8'),tree=ts.createSourceFile('EmailForms.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),cases=[];
const declaration=name=>tree.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text===name);
function child(node,name){return node.body.statements.find(item=>ts.isFunctionDeclaration(item)&&item.name?.text===name)}
function compile(node,scope,name){const js=ts.transpileModule(node.getText(),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None}}).outputText;return new Function(...Object.keys(scope),js+';return '+name)(...Object.values(scope))}
function session(){
 const state={token:'A',active:true},effects=[],states=[],refs=[];let si=0,ri=0;
 const hooks={useRef:value=>refs[ri++]??(refs[ri-1]={current:value}),useState:value=>{const index=si++;if(!(index in states))states[index]=value;return[states[index],next=>states[index]=typeof next==='function'?next(states[index]):next]},useEffect:fn=>effects.push(fn),getToken:()=>state.token,window:{setInterval:()=>1,clearInterval(){},addEventListener(){},removeEventListener(){}}};
 const hook=compile(declaration('useEmailForm'),hooks,'useEmailForm'),render=()=>{si=0;ri=0;return hook(()=>state.active)};let scope=render();const cleanups=effects.map(effect=>effect()).filter(Boolean);
 return {state,states,render,scope,cleanup:()=>cleanups.forEach(fn=>fn())};
}
function formEnvironment(component,enabled=true){
 const s=session(),events=[],requests=[],fields={email:'owner@example.test',code:'123456',new_password:'REDACTED_SECRET',confirm:'SyntheticNewPassword42',current_password:'REDACTED_SECRET'};
 const env={...s,events,requests,fields,enabled:true};
 const scope={enabled,scope:s.scope,email:{current:{value:fields.email,reportValidity:()=>true}},draftEmail:fields.email,resetCodeNotice:'如果该邮箱已验证并关联可用账户，验证码会发送至该邮箱，请稍后查收。',form:{current:{reset:()=>events.push(['reset'])}},FormData:class{get(key){return fields[key]}},api:(url,options)=>new Promise((resolve,reject)=>requests.push({url,body:JSON.parse(options.body),resolve,reject})),onSuccess:()=>events.push(['success'])};
 for(const name of ['setError','setMessage','setStatus','setDraftEmail'])scope[name]=value=>events.push([name,value]);
 for(const name of ['sendCode',component==='ForgotPasswordForm'?'submit':'verify'])env[name]=compile(child(declaration(component),name),scope,name);
 env.run=()=>env[component==='ForgotPasswordForm'?'submit':'verify']({preventDefault(){}});return env;
}
(async()=>{
 {
  const e=session(),first=e.scope.start('send');assert(first);assert.equal(e.scope.start('submit'),null);first.finish();assert(e.scope.start('submit'));e.cleanup();cases.push('actual form scope synchronously locks send and submit until the active request finishes');
 }
 {
  const e=session(),now=Date.now();e.scope.cooldown();const rendered=e.render();assert(rendered.seconds>=59&&rendered.seconds<=60);assert(e.states[1]>=now+60000);e.cleanup();cases.push('cooldown uses an absolute 60-second deadline rather than input contents or decrement-only timers');
 }
 for(const mode of ['route','token','unmount']){
  const e=session(),action=e.scope.start('send');if(mode==='route')e.state.active=false;if(mode==='token')e.state.token='B';if(mode==='unmount')e.cleanup();assert.equal(action.valid(),false);if(mode==='unmount')assert(action.signal.aborted);else e.cleanup();
 }
 cases.push('route change, token replacement and unmount invalidate late responses; cleanup aborts the actual request signal');
 {
  const e=formEnvironment('ForgotPasswordForm');e.fields.confirm='different';await e.run();assert.equal(e.requests.length,0);assert(e.events.some(row=>row[0]==='setError'));e.cleanup();cases.push('mismatched reset passwords never send a reset request');
 }
 {
  const e=formEnvironment('ForgotPasswordForm'),one=e.sendCode(),two=e.sendCode();assert.equal(e.requests.length,1);e.requests[0].resolve({message:'generic'});await one;await two;assert(e.events.some(row=>row[0]==='setMessage'&&row[1].includes('如果该邮箱')));assert(!JSON.stringify(e.events).includes(e.fields.email));e.cleanup();cases.push('duplicate reset-code clicks send once and show a fixed non-enumerating response');
 }
 {
  const e=formEnvironment('ForgotPasswordForm'),pending=e.run();assert.deepEqual(Object.keys(e.requests[0].body).sort(),['code','email','new_password']);e.requests[0].reject(Error('sensitive server data '+e.fields.code+' '+e.fields.new_password));await pending;assert(!JSON.stringify(e.events).includes(e.fields.code));assert(!JSON.stringify(e.events).includes(e.fields.new_password));assert(!e.events.some(row=>row[0]==='success'));e.cleanup();cases.push('reset errors use safe fixed feedback and never echo passwords or codes');
 }
 {
  const e=formEnvironment('ForgotPasswordForm'),pending=e.run();e.state.active=false;e.requests[0].resolve({message:'updated'});await pending;assert(!e.events.some(row=>row[0]==='success'||row[0]==='reset'));e.cleanup();cases.push('late reset success after leaving the public page cannot clear credentials or navigate the new page');
 }
 {
  const e=formEnvironment('AccountEmailSettings'),pending=e.run();assert.equal(e.requests[0].url,'/auth/email/verify');assert.equal(e.requests[0].body.current_password,e.fields.current_password);e.state.token='B';e.requests[0].resolve({email:'new@example.test',verified:true});await pending;assert(!e.events.some(row=>row[0]==='setStatus'||row[0]==='reset'));e.cleanup();cases.push('email binding supplies current-password proof and never updates another account after token replacement');
 }
 {
  const e=formEnvironment('AccountEmailSettings'),pending=e.run();e.requests[0].resolve({email:'new@example.test',verified:true});await pending;assert(e.events.some(row=>row[0]==='setStatus'&&row[1].verified===true));assert(e.events.some(row=>row[0]==='reset'));e.cleanup();cases.push('successful verified binding updates the stored email state and clears proof inputs');
 }

 for(const component of ['ForgotPasswordForm','AccountEmailSettings']){
  const e=formEnvironment(component,false);await e.sendCode();await e.run();assert.equal(e.requests.length,0);e.cleanup();
 }
 cases.push('disabled SMTP feature prevents both code and proof/reset POSTs independently of the registration switch');
 {
  const e=formEnvironment('ForgotPasswordForm'),pending=e.run();e.requests[0].resolve({message:'updated'});await pending;assert(e.events.some(row=>row[0]==='reset'));assert(e.events.some(row=>row[0]==='success'));assert.equal(e.requests.length,1);assert.equal(e.requests[0].url,'/auth/password-reset');e.cleanup();cases.push('successful reset clears proof inputs and delegates return-to-login without making a login request');
 }
 fs.writeFileSync('.runtime/email-auth-20261029/desktop-form-checks.json',JSON.stringify({status:'passed',source:'actual TSX form methods and actual lifetime/lock/cooldown hook',cases,production_network_called:false,smtp_mail_sent:false},null,2));console.log(JSON.stringify({status:'passed',cases:cases.length}));
})().catch(error=>{console.error(error);process.exitCode=1});
