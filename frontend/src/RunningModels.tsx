import type {ActiveModel,ModelComponent,ModelInfo} from './types'
import {confidenceText} from './predictionFormat'
import './model-verification.css'

type RunningComponent=ModelComponent|(ActiveModel&{role?:undefined;status:string})
export default function RunningModels({model}:{model:ModelInfo}){
  const active=model.active
  if(!active)return null
  const components:RunningComponent[]=active.components?.length?active.components:[{...active,role:undefined,status:model.status}]
  return <section className="running-models" aria-label="实际运行的模型组件">
    <div className="running-models-heading"><h2>实际运行的模型</h2><p>{active.pipeline==='detection_with_classification'?'目标检测提供定位框与主要结论；分类模型独立复核整张图片，结果分别记录。':'当前推理服务加载的模型，不依赖下方手动上传登记列表。'}</p></div>
    <div className="running-model-grid">{components.map((item,index)=>{
      const verification=item.role==='verification'
      const role=verification?'整图分类复核':item.task==='detect'?'目标检测':'图像分类'
      const ready=item.status==='ready'
      return <article className="running-model-card" key={`${item.role??item.task}:${item.onnx_sha256??index}`}>
        <div className="running-model-heading"><strong>{role}</strong><span className={`badge ${ready?'healthy':'awaiting_model'}`}>{ready?'运行中':item.status==='unavailable'?'暂不可用':'未就绪'}</span></div>
        <h3>{item.name}</h3><p>{verification?'输入范围：整张图片，不逐框分类。':item.task==='detect'?'输出范围：检测目标框与对应类别。':item.scope}</p>
        <dl><div><dt>模型类别</dt><dd>{item.class_count} 类</dd></div>{item.task==='detect'?<div><dt>独立检测 mAP</dt><dd>尚未提供</dd></div>:<><div><dt>独立测试集 Top1</dt><dd>{confidenceText(item.test_top1)}</dd></div><div><dt>宏平均 F1</dt><dd>{confidenceText(item.test_macro_f1)}</dd></div></>}</dl>
        {item.onnx_sha256&&<details className="running-model-hash"><summary>模型文件校验</summary><code>SHA256 {item.onnx_sha256}</code></details>}
      </article>
    })}</div>
    <p className="running-models-note">各模型分数和评估指标只对应各自任务，不合并，也不代表田间准确率。</p>
  </section>
}
