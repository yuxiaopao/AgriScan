// Render the actual shared React components; no DOM automation or provider calls.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const localRequire=createRequire(path.resolve('frontend/package.json'));
const React=localRequire('react');
const {renderToStaticMarkup}=localRequire('react-dom/server');
const esbuild=localRequire('esbuild');
function load(entry){
  const output=esbuild.buildSync({entryPoints:[entry],bundle:true,write:false,platform:'node',format:'cjs',packages:'external',jsx:'automatic',loader:{'.css':'empty'}}).outputFiles[0].text;
  const mod={exports:{}};new Function('require','module','exports',output)(localRequire,mod,mod.exports);return mod.exports;
}
const {PredictionScores}=load('frontend/src/PredictionScores.tsx');
const {default:RunningModels}=load('frontend/src/RunningModels.tsx');
const render=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
const candidate={key:'Apple___Apple_scab',crop:'苹果',label:'苹果黑星病',healthy:false,confidence:.846};
const classification={...candidate,confidence:.9234,candidates:[{...candidate,confidence:.9234},{...candidate,key:'Apple___healthy',label:'苹果健康',healthy:true,confidence:.0766}]};
const verification={status:'agree',scope:'whole_image',message:'同一叶片的目标检测与整图分类一致。',model:{name:'PlantVillage classifier fixture',task:'classify',onnx_sha256:'b'.repeat(64)},detection:candidate,classification};
const record={id:'fixture',name:'leaf-fixture.jpg',crop:'苹果',plot_id:null,plot_name:'',status:'attention',result:'苹果黑星病',confidence:.846,created_at:'2026-10-29T00:00:00Z',image_url:null,is_demo:false,note:'',candidates:[candidate],boxes:[{...candidate,class_id:0,bbox:[.1,.1,.9,.9]}],prediction_model:{name:'Leaf detector fixture',task:'detect',onnx_sha256:'a'.repeat(64),verification}};
const cases=[];
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value)}return value}
{
  const immutable=freeze(structuredClone(record)),before=JSON.stringify(immutable),html=render(PredictionScores,{record:immutable});
  assert(html.includes('两模型一致')&&html.includes('84.60%')&&html.includes('92.34%'));
  assert(!html.includes('88.47%'));assert(html.includes('整张图片')&&html.includes('不是逐框分类'));
  assert.equal(JSON.stringify(immutable),before);cases.push('agree shows both original scores without averaging or mutating detection/boxes');
}
for(const [status,label] of [['disagree','结果不一致，建议复核'],['uncertain','需人工复核'],['unavailable','分类复核暂不可用']]){
  const value=structuredClone(record);value.prediction_model.verification.status=status;
  if(status==='unavailable')value.prediction_model.verification.classification=null;
  const html=render(PredictionScores,{record:value});assert(html.includes(label)&&html.includes('84.60%'));
  if(status==='unavailable')assert(html.includes('暂无分类复核分数')&&!html.includes('92.34%'));
  cases.push(status+' is explicit and retains the detector score');
}
{
  const value=structuredClone(record);value.candidates=[];
  assert(render(PredictionScores,{record:value}).includes('整图分类复核'));cases.push('verification renders even when main candidates are absent');
}
{
  const value=structuredClone(record);delete value.prediction_model.verification;
  const html=render(PredictionScores,{record:value});assert(!html.includes('整图分类复核')&&html.includes('84.60%'));
  value.candidates=[];assert.equal(render(PredictionScores,{record:value}),'');cases.push('historical snapshots without verification keep their original display');
}
{
  const base={name:'Best leaf detector fixture',task:'detect',onnx_sha256:'a'.repeat(64),class_count:38,test_top1:null,test_macro_f1:null,scope:'Detection fixture'};
  const model={active:{...base,pipeline:'detection_with_classification',components:[{...base,role:'detection',status:'ready'},{...base,name:'PlantVillage classifier fixture',task:'classify',role:'verification',status:'ready',onnx_sha256:'b'.repeat(64),test_top1:.944,test_macro_f1:.936}]},items:[],status:'ready',message:'',supported_crops:['苹果'],available_crops:['苹果']};
  const html=render(RunningModels,{model});assert(html.includes('目标检测')&&html.includes('整图分类复核'));
  assert(html.includes(base.name)&&html.includes('PlantVillage classifier fixture')&&html.includes('a'.repeat(64))&&html.includes('b'.repeat(64)));
  assert(html.includes('94.40%')&&html.includes('93.60%')&&html.includes('独立检测 mAP'));
  cases.push('both active components render with task-specific metrics when upload items is empty');
  model.active={...base};const legacy=render(RunningModels,{model});assert(legacy.includes('目标检测')&&!legacy.includes('整图分类复核'));
  cases.push('legacy active model does not fabricate a second running component');
}
const report={status:'passed',source:'actual PredictionScores/ModelVerification/RunningModels bundled in memory and rendered with React server renderer',cases,network_called:false,browser_ui_tested:false};
fs.writeFileSync('.runtime/dual-model-20261029/web-contract-checks.json',JSON.stringify(report,null,2));
console.log(JSON.stringify({status:'passed',cases:cases.length,report:'.runtime/dual-model-20261029/web-contract-checks.json'}));
