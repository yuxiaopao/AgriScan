import {Empty} from './components'
import {IpIcon} from './IpIcon'
import type {ModelInfo} from './types'
import './model-verification.css'

export default function ModelsPage({model}: {model: ModelInfo | null}) {
  const active = model?.active
  const components = active ? active.components?.length ? active.components : [active] : []
  const dual = active?.pipeline === 'detection_with_classification' && components.some(component => component.role === 'verification')
  return <div className="model-service-page">
    <div className="page-intro"><span className="eyebrow">这次观察，怎样识别</span><h1><IpIcon name="detect"/>识别服务</h1><p>{dual ? '一个模型定位目标，一个模型复核整图分类。' : '查看当前识别能力与服务状态。'}</p></div>
    {!active ? <Empty title={model ? '识别模型尚未启用' : '暂未读取到识别服务'} text={model ? model.message : '请返回首页刷新，或到连接设置中检查网络。'}/> : <>
      <p className="model-service-note">{model?.message}</p>
      <div className="model-component-list">{components.map(component => {
        const classifier = component.role === 'verification' || component.task === 'classify'
        const ready = component.status ? component.status === 'ready' : model?.status === 'ready'
        return <section className="model-component-card" key={`${component.role || component.task}:${component.onnx_sha256 || component.name}`}>
          <header><span>{classifier ? '整图分类复核' : '叶片目标检测'}</span><strong className={`badge ${ready ? 'healthy' : 'attention'}`}>{ready ? '已就绪' : '待恢复'}</strong></header>
          <h2>{component.name}</h2><p>{component.scope}</p>
          <dl><div><dt>覆盖类别</dt><dd>{component.class_count} 类</dd></div><div><dt>识别方式</dt><dd>{classifier ? '整图单标签分类' : '目标框与类别'}</dd></div>{component.image_size && <div><dt>模型输入</dt><dd>{component.image_size} × {component.image_size}</dd></div>}</dl>
          <p className="model-component-scope">{classifier ? '对整张照片输出分类候选，不新增定位框；单叶照片更适合此项复核。' : '框表示模型识别的目标范围，不是病斑的精确边界或面积。'}</p>
          {component.onnx_sha256 && <details><summary>查看模型标识</summary><code>{component.onnx_sha256}</code></details>}
        </section>
      })}</div>
      {dual && <p className="model-service-note">两模型分数分别呈现；结果有分歧或复核失败时，会在观察报告中明确提示。历史记录保留当次模型结果。</p>}
      <p className="fine-print">类别覆盖不等于田间准确率。检测框、分类结果和照片观察都需结合现场情况判断。</p>
    </>}
  </div>
}
