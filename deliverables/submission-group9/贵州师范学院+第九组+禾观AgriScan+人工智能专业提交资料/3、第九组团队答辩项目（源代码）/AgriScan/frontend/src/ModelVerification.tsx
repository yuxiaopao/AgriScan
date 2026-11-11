import type {ModelVerificationInfo} from './types'
import {confidenceText} from './predictionFormat'
import './model-verification.css'

const states:Record<ModelVerificationInfo['status'],string>={
  agree:'两模型一致',disagree:'结果不一致，建议复核',uncertain:'需人工复核',unavailable:'分类复核暂不可用',
}

/** Detection stays authoritative; this independent classification covers the complete image. */
export default function ModelVerification({verification,compact=false}:{verification?:ModelVerificationInfo;compact?:boolean}){
  if(!verification)return null
  const classification=verification.classification
  const tone=verification.status==='agree'?'healthy':verification.status==='unavailable'?'awaiting_model':'attention'
  return <section className={`model-verification ${compact?'compact':''}`} aria-label="目标检测与整图分类复核">
    <div className="verification-heading"><h3>整图分类复核</h3><span className={`verification-state badge ${tone}`}>{states[verification.status]}</span></div>
    <div className="verification-model-results">
      <div><span className="verification-role">目标检测</span><strong>{verification.detection.label}</strong><small>{verification.detection.crop}</small><dl><dt>目标置信度</dt><dd title={`检测原始分数：${verification.detection.confidence}`}>{confidenceText(verification.detection.confidence)}</dd></dl></div>
      <div><span className="verification-role">整图分类复核</span>{classification?<><strong>{classification.label}</strong><small>{classification.crop}</small><dl><dt>原始分类分数</dt><dd title={`分类原始分数：${classification.confidence}`}>{confidenceText(classification.confidence)}</dd></dl></>:<p className="verification-missing">暂无分类复核分数，请结合目标检测与现场情况复核。</p>}</div>
    </div>
    <p className="verification-message">{verification.message}</p>
    <p className="verification-explanation">分类模型独立检查整张图片，不是逐框分类。两模型分数分别保留，不平均，也不表示实际准确率。</p>
    {!compact&&classification?.candidates.length? <details className="verification-candidates"><summary>查看分类复核候选</summary><ol>{classification.candidates.map((item,index)=><li key={`${item.key}:${index}`}><span>{item.label}</span><strong title={`分类原始分数：${item.confidence}`}>{confidenceText(item.confidence)}</strong></li>)}</ol><p>候选是单标签分类的替代判断，不代表同时患有多种病害。</p></details>:null}
    {!compact&&<small className="verification-model-name">复核模型：{verification.model.name}</small>}
  </section>
}
