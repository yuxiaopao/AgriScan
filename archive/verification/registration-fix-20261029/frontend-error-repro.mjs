import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {runInNewContext} from 'node:vm'

const require=createRequire(new URL('../../frontend/package.json',import.meta.url))
const ts=require('typescript')
const shared=new Map()
function loadShared(name){
  const key=name.split('/').pop()
  if(shared.has(key))return shared.get(key)
  const raw=readFileSync(new URL(`../../shared/${key}.ts`,import.meta.url),'utf8')
  const js=ts.transpileModule(raw,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  const exported={};runInNewContext(js,{exports:exported,require:loadShared});shared.set(key,exported);return exported
}
const detail=[{type:'string_pattern_mismatch',loc:['body','username'],msg:"String should match pattern '^[a-zA-Z0-9_-]+$'",input:'synthetic@example.com'}]
for(const surface of ['frontend','mobile']){
  const raw=readFileSync(new URL(`../../${surface}/src/api.ts`,import.meta.url),'utf8').replaceAll('import.meta.env','({})')
  const js=ts.transpileModule(raw,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  const storage={getItem:()=>null,setItem(){},removeItem(){}}
  const exported={}
  const ctx={exports:exported,require:loadShared,sessionStorage:storage,localStorage:storage,Headers,FormData,AbortSignal,DOMException,URL,Event,window:{dispatchEvent(){}},fetch:async()=>({ok:false,status:422,json:async()=>({detail})})}
  runInNewContext(js,ctx)
  await assert.rejects(exported.api('/auth/register',{method:'POST',body:'{}'}),error=>{
    console.log(`${surface}: ${error.message}`)
    assert(!error.message.includes('String should match pattern'),'English Pydantic schema message leaked to user')
    return true
  })
}
