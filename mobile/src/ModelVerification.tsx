import {confidence} from './hooks'
import {IpIcon} from './IpIcon'
import type {ModelVerificationInfo} from './types'
import './model-verification.css'

const states = {
  agree: {title: '两模型判断一致', note: '结果一致仍需结合叶片与现场情况确认。'},
  disagree: {title: '两模型存在分歧', note: '请人工复核，补拍清晰单叶照片后再检测。'},
  uncertain: {title: '整图复核尚不确定', note: '暂不作为确定结论，建议改善光线后复拍。'},
  unavailable: {title: '整图复核暂不可用', note: '下方仅保留目标检测结果，请稍后重新检测。'},
} as const

export function ModelVerification({verification, compact = false}: {verification?: ModelVerificationInfo; compact?: boolean}) {
  if (!verification) return null
  const state = states[verification.status] ?? states.uncertain
  const classification = verification.classification
  return <section className={`model-verification verification-${verification.status}${compact ? ' is-compact' : ''}`} aria-label="双模型复核">
    <header><IpIcon name="detect"/><div><span>目标检测 · 整图分类复核</span><h3>{state.title}</h3></div></header>
    <p className="verification-message">{verification.message || state.note}</p>
    <dl className="verification-scores">
      <div><dt>检测主目标</dt><dd><strong>{verification.detection.label}</strong><span title={`目标检测独立分数 ${verification.detection.confidence}`}>{confidence(verification.detection.confidence)}<small>目标置信度</small></span></dd></div>
      <div><dt>整图分类</dt><dd><strong>{classification?.label || '未取得分类结果'}</strong><span title={classification ? `整图单标签分类概率 ${classification.confidence}` : undefined}>{classification ? confidence(classification.confidence) : '—'}<small>分类置信度</small></span></dd></div>
    </dl>
    <p className="verification-scope">分类针对整张照片，并非逐框复核。两类分数分别计算，不融合为综合置信度。</p>
    {verification.status !== 'agree' && <p className="verification-action">{state.note}</p>}
    {!compact && <details className="verification-details"><summary>查看分类模型与候选</summary><p>{verification.model.name}</p>{!!classification?.candidates?.length && <><ol>{classification.candidates.map(candidate => <li key={candidate.key}><span>{candidate.label}</span><strong>{confidence(candidate.confidence)}</strong></li>)}</ol><p>候选为单标签分类的替代判断，不表示同时患有多种病。</p></>}</details>}
  </section>
}
