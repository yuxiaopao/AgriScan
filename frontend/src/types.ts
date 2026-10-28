export type Page = 'dashboard' | 'detect' | 'records' | 'plots' | 'knowledge' | 'models' | 'settings'
export type DetectionStatus = 'healthy' | 'attention' | 'awaiting_model' | 'queued' | 'processing' | 'failed'
export interface DetectionBox {
  class_id:number
  key:string
  label:string
  crop:string
  healthy:boolean
  confidence:number
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
  candidates?: {key: string; label: string; crop: string; healthy: boolean; confidence: number}[]
  boxes?:DetectionBox[]
  prediction_model?: {name: string; task: string; onnx_sha256: string} | null
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
export interface ModelInfo {active: {name: string; task: string; class_count: number; test_top1: number | null; test_macro_f1: number | null; scope: string} | null; items: unknown[]; supported_crops: string[]; available_crops: string[]; status: string; message: string}
export interface Article {id: string; title: string; crop: string; category: string; summary: string; content: string; image: string | null; sources?: {title: string; url: string}[]}
export interface User {name: string; role: string; username: string}
