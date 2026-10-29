export type Page = 'dashboard' | 'detect' | 'records' | 'plots' | 'knowledge' | 'models' | 'settings'
export type DetectionStatus = 'healthy' | 'attention' | 'awaiting_model' | 'queued' | 'processing' | 'failed'
export interface Candidate {
  key:string
  label:string
  crop:string
  healthy:boolean
  confidence:number
}
export interface ModelVerificationInfo {
  status:'agree'|'disagree'|'uncertain'|'unavailable'
  scope:'whole_image'
  message:string
  model:{name:string;task:'classify';onnx_sha256:string}
  detection:Candidate
  classification:(Candidate & {candidates:Candidate[]})|null
}
export interface PredictionModelSnapshot {
  name:string
  task:string
  onnx_sha256:string
  verification?:ModelVerificationInfo
}
export interface DetectionBox extends Candidate {
  class_id:number
  /** Normalized xyxy in the server-saved, EXIF-oriented original image. */
  bbox:[number,number,number,number]
}
export interface Detection {
  id: string
  name: string
  crop: string
  plot_id: string | null
  plot_name: string
  status: DetectionStatus
  result: string | null
  confidence: number | null
  candidates?: Candidate[]
  boxes?:DetectionBox[]
  prediction_model?: PredictionModelSnapshot | null
  created_at: string
  image_url: string | null
  is_demo: boolean
  note: string
}
export interface Plot {
  id: string
  name: string
  crop: string
  area: number
  location: string
  manager: string
  cover_url?: string | null
  latitude?: number | null
  longitude?: number | null
  health_score: number | null
  detections: number
}
export interface Dashboard {
  stats: {total: number; healthy: number; attention: number; pending: number}
  trend: {label: string; total: number; healthy: number}[]
  distribution: {name: string; value: number; color: string}[]
  recent: Detection[]
}
export interface Health {status: string; database: string; redis: string; mode: string; model: string}
export interface ActiveModel {
  name:string;task:string;class_count:number;test_top1:number|null;test_macro_f1:number|null;scope:string
  onnx_sha256?:string;pipeline?:'detection_with_classification';components?:ModelComponent[]
}
export interface ModelComponent extends Omit<ActiveModel,'pipeline'|'components'> {
  role:'detection'|'verification';status:string;onnx_sha256:string
}
export interface ModelInfo {active:ActiveModel|null;items:unknown[];supported_crops:string[];available_crops:string[];status:string;message:string}
export interface Article {id: string; title: string; crop: string; category: string; summary: string; content: string; image: string | null; sources?: {title: string; url: string}[]}
export interface User {name: string; role: string; username: string}
