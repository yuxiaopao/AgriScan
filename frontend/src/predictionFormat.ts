export function confidenceText(score:number|null|undefined):string {
  if (score==null||!Number.isFinite(score)) return '—'
  if (score===1) return '≈100%'
  if (score>0.9999) return '>99.99%'
  if (score>0&&score<0.0001) return '<0.01%'
  return `${(score*100).toFixed(2)}%`
}
