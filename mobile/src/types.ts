export interface User {name: string; username: string; role: string}
export interface AuthConfig {registration_enabled: boolean; email_verification_enabled: boolean; password_reset_enabled: boolean}
export interface Candidate {key: string; label: string; crop: string; healthy: boolean; confidence: number}
export interface ModelVerificationInfo {
  status: 'agree' | 'disagree' | 'uncertain' | 'unavailable'
  scope: 'whole_image'
  message: string
  model: {name: string; task: 'classify'; onnx_sha256: string}
  detection: Candidate
  classification: (Candidate & {candidates: Candidate[]}) | null
}
export interface ModelComponent {
  name: string; task: string; class_count: number; scope: string; onnx_sha256?: string
  role?: 'detection' | 'verification'; status?: string; image_size?: number; threshold?: number
  test_top1?: number | null; test_macro_f1?: number | null
}
export interface DetectionBox extends Candidate {class_id:number;bbox:[number,number,number,number]}
export interface Detection {id: string; name: string; crop: string; plot_id: string | null; plot_name: string; status: string; result: string | null; confidence: number | null; created_at: string; image_url: string | null; is_demo: boolean; note: string; candidates?: Candidate[]; boxes?:DetectionBox[]; prediction_model?: {name: string; task: 'classify'|'detect'|string; onnx_sha256: string; verification?: ModelVerificationInfo} | null}
export interface Plot {id: string; name: string; crop: string; area: number; location: string; manager: string; cover_url?: string | null; latitude?: number | null; longitude?: number | null; health_score: number | null; detections: number}
export interface ModelInfo {status: string; message: string; available_crops: string[]; supported_crops: string[]; active: (ModelComponent & {pipeline?: 'detection_with_classification'; components?: ModelComponent[]}) | null}
export interface Article {id: string; title: string; crop: string; category: string; summary: string; content: string; sources?: {title: string; url: string}[]}
export interface Conversation {id: string; title: string; updated_at: string}
export interface ChatMessage {id: number; role: 'user' | 'assistant'; content: string; created_at: string}
export interface ChatDetail {conversation: Conversation; messages: ChatMessage[]}
export interface VideoResult {id: string; filename: string; duration_seconds: number; sampled_frames: number; results: {timestamp_seconds: number; detection: Detection}[]; summary: {total: number; healthy: number; attention: number}; source: 'sampled_video'}
export interface Workspace {records: Detection[]; plots: Plot[]; articles: Article[]; model: ModelInfo | null}
export interface MediaCapabilities {video_max_mb:number;video_max_seconds:number;video_max_frames:number;frame_min_interval_ms:number;video_enabled:boolean;live_enabled:boolean;model_ready:boolean;mode:string}
export const emptyWorkspace: Workspace = {records: [], plots: [], articles: [], model: null}
