import type {Detection} from './types'

export function confidenceText(score: number | null): string {
  if (score == null || !Number.isFinite(score)) return '—'
  if (score === 1) return '≈100%'
  if (score > 0.9999) return '>99.99%'
  if (score > 0 && score < 0.0001) return '<0.01%'
  return `${(score * 100).toFixed(2)}%`
}

export function PredictionScores({record}: {record: Detection}) {
  if (!record.candidates?.length) return null
  return <section className="prediction-scores" aria-label="模型候选结果">
    <div className="prediction-heading"><h3>候选结果</h3><span>前 {record.candidates.length} 项 · 原始分数</span></div>
    <ol>{record.candidates.map((item, index) => <li key={item.key}>
      <div><span><i>{index + 1}</i>{item.label}</span><strong title={`模型原始输出：${item.confidence}`}>{confidenceText(item.confidence)}</strong></div>
      <div className="prediction-track" aria-hidden="true"><span style={{width: `${item.confidence * 100}%`}}/></div>
    </li>)}</ol>
    <p>这些是单标签模型的候选判断，不代表同时患有多种病害。分数未重新归一化；高置信度也不等于确诊或实际准确率。</p>
  </section>
}
