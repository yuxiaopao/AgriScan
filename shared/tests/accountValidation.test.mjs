import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {fileURLToPath} from 'node:url'
import {runInThisContext} from 'node:vm'

const requireFrontend=createRequire(new URL('../../frontend/package.json',import.meta.url))
const ts=requireFrontend('typescript')
const modules=new Map()
function load(relative){
  if(modules.has(relative))return modules.get(relative)
  const url=new URL(`../${relative}.ts`,import.meta.url)
  const compiled=ts.transpileModule(readFileSync(url,'utf8'),{
    compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS},fileName:fileURLToPath(url),
  }).outputText
  const exports={}
  runInThisContext(`(function(exports,require){${compiled}\n})`,{filename:fileURLToPath(url)})(exports,name=>load(name.replace(/^\.\//,'')))
  modules.set(relative,exports)
  return exports
}
const {registrationUsernameError,USERNAME_ERROR}=load('accountValidation')
const {apiErrorMessage}=load('apiErrors')

test('registration accepts both ordinary and email-form usernames through 80 characters',()=>{
  for(const username of ['member_1','field-member','123','Farmer','synthetic@example.com','a.b+tag@farm.example','x'.repeat(80),'a'.repeat(64)+'@example.com']){
    assert.equal(registrationUsernameError(username),'',username)
  }
})

test('registration rejects unsupported identifiers and malformed email-form usernames',()=>{
  for(const username of ['ab','x'.repeat(81),'用户一','a b',' member','member ','a@@example.com','a@example','a..b@example.com','.a@example.com','a.@example.com','a@-example.com','a@example-.com','a@ex_ample.com','a@exa..com','a'.repeat(65)+'@example.com','a@'+'x'.repeat(64)+'.com']){
    assert.equal(registrationUsernameError(username),USERNAME_ERROR,username)
  }
})

test('Pydantic username pattern failure becomes actionable Chinese without raw input or pattern',()=>{
  const message=apiErrorMessage([{loc:['body','username'],type:'string_pattern_mismatch',msg:"String should match pattern '^[a-zA-Z0-9_-]+$'",input:'PRIVATE-VALUE',ctx:{pattern:'PRIVATE-PATTERN'}}],'Fallback')
  assert.equal(message,USERNAME_ERROR)
  assert(!message.includes('PRIVATE'))
  assert(!message.includes('String should match'))
})

test('common account validation failures identify the field in Chinese',()=>{
  const item=(field,type,ctx)=>[{loc:['body',field],type,ctx,msg:'Technical validation message',input:'PRIVATE'}]
  assert.equal(apiErrorMessage(item('password','string_too_short',{min_length:10}),'Fallback'),'密码至少需要 10 个字符。')
  assert.equal(apiErrorMessage(item('new_password','string_too_long',{max_length:128}),'Fallback'),'新密码不能超过 128 个字符。')
  assert.equal(apiErrorMessage(item('email','string_pattern_mismatch'),'Fallback'),'请填写有效的邮箱地址。')
  assert.equal(apiErrorMessage(item('code','string_pattern_mismatch'),'Fallback'),'请填写邮件中的 6 位数字验证码。')
  assert.equal(apiErrorMessage(item('name','missing'),'Fallback'),'请填写昵称。')
})

test('Chinese server detail is retained and unknown schema errors have a safe fallback',()=>{
  assert.equal(apiErrorMessage('该用户名已被使用。','Fallback'),'该用户名已被使用。')
  assert.equal(apiErrorMessage([{msg:'Value error, 请同时填写经度和纬度。',type:'value_error'}],'Fallback'),'请同时填写经度和纬度。')
  assert.equal(apiErrorMessage([{loc:['body','unknown'],msg:'PRIVATE',input:'PRIVATE'}],'Fallback'),'填写内容格式不正确，请检查后重试。')
  assert.equal(apiErrorMessage([{loc:['body','constructor'],msg:'PRIVATE',input:'PRIVATE'}],'Fallback'),'填写内容格式不正确，请检查后重试。')
  assert.equal(apiErrorMessage([{type:'string_pattern_mismatch',msg:"String should match pattern 'PRIVATE中文'"}],'Fallback'),'填写内容格式不正确，请检查后重试。')
  assert.equal(apiErrorMessage(null,'Fallback'),'Fallback')
  assert.equal(apiErrorMessage([],'Fallback'),'Fallback')
  assert.equal(apiErrorMessage([null,{},{}],'Fallback'),'填写内容不符合要求，请检查后重试。；填写内容格式不正确，请检查后重试。')
})

test('validation messages are deduplicated and bounded',()=>{
  const detail=Array.from({length:20},()=>({loc:['body','email'],type:'string_pattern_mismatch',msg:'PRIVATE'}))
  assert.equal(apiErrorMessage(detail,'Fallback'),'请填写有效的邮箱地址。')
})
