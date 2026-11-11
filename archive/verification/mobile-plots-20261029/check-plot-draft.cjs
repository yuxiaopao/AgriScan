const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path')
const root='E:/AgriScan',esbuild=require(root+'/mobile/node_modules/esbuild')
const source=fs.readFileSync(root+'/mobile/src/plotDraft.ts','utf8'),compiled={exports:{}}
new Function('module','exports',esbuild.transformSync(source,{loader:'ts',format:'cjs',target:'es2022'}).code)(compiled,compiled.exports)
const {plotBody,plotDraft}=compiled.exports,crops=['苹果','玉米'],base={name:' 东侧果园 ',crop:'苹果',area:'2.5',location:' 田间路口 ',manager:' 巡田伙伴 ',latitude:'',longitude:''},checks=[]
const check=(name,fn)=>{fn();checks.push(name)}
const body=plotBody(base,crops)
check('trimmed personal fields and finite acreage',()=>assert.deepEqual(body,{name:'东侧果园',crop:'苹果',area:2.5,location:'田间路口',manager:'巡田伙伴',latitude:null,longitude:null}))
check('no owner or administrative field is emitted',()=>assert.deepEqual(Object.keys(body).sort(),['area','crop','latitude','location','longitude','manager','name']))
check('zero coordinates are preserved',()=>assert.equal(plotBody({...base,latitude:'0',longitude:'0'},crops).longitude,0))
check('coordinate boundary pair is valid',()=>assert.deepEqual([plotBody({...base,latitude:'-90',longitude:'180'},crops).latitude,plotBody({...base,latitude:'-90',longitude:'180'},crops).longitude],[-90,180]))
for(const [label,change] of [['blank name',{name:' '}],['long name',{name:'果'.repeat(101)}],['unsupported crop',{crop:'unknown'}],['zero area',{area:'0'}],['negative area',{area:'-1'}],['non-finite area',{area:'Infinity'}],['oversized area',{area:'1000001'}],['latitude only',{latitude:'1'}],['longitude only',{longitude:'2'}],['invalid latitude',{latitude:'NaN',longitude:'2'}],['latitude overflow',{latitude:'91',longitude:'2'}],['longitude overflow',{latitude:'2',longitude:'181'}],['long location',{location:'地'.repeat(201)}],['long manager',{manager:'人'.repeat(81)}]])check('reject '+label,()=>assert.throws(()=>plotBody({...base,...change},crops)))
check('edit draft retains existing fields and coordinates',()=>{const draft=plotDraft({id:'own',...body,latitude:0,longitude:121,health_score:null,detections:0},'玉米','Other');assert.equal(draft.latitude,'0');assert.equal(draft.name,'东侧果园');assert.equal(draft.crop,'苹果')})
fs.writeFileSync(path.join(__dirname,'draft-checks.json'),JSON.stringify({status:'passed',source:'actual mobile/src/plotDraft.ts pure functions',checks,count:checks.length,request_body:body},null,2))
console.log(JSON.stringify({status:'passed',count:checks.length}))
