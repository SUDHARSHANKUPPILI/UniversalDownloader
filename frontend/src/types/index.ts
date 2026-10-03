export interface UrlAnalysis {
  valid: boolean;
  title?: string;
  uploader?: string;
  duration?: number;
  thumbnail?: string;
  is_playlist?: boolean;
  playlist_count?: number;
  webpage_url?: string;
  formats_count?: number;
  description?: string;
  upload_date?: string;
  view_count?: number;
  channel_url?: string;
  error?: string;
}

export interface Download {
  id: number;
  url: string;
  title: string;
  media_type: string;
  quality: string;
  format: string;
  subtitle_languages: string | null;
  save_location: string;
  status: 'queued' | 'downloading' | 'paused' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  total_size: number | null;
  downloaded_size: number | null;
  speed: number | null;
  eta_seconds: number | null;
  thumbnail: string | null;
  duration: number | null;
  uploader: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  retry_count: number;
  max_retries: number;
  source_hash: string;
  file_hash: string | null;
  is_duplicate: number;
}

export interface QueueItem {
  id: number;
  download_id: number;
  position: number;
  status: string;
  claimed_by: string | null;
  claimed_at: string | null;
  created_at: string;
  updated_at: string;
  title: string;
  download_status: string;
  media_type: string;
  quality: string;
  format: string;
  progress: number;
  total_size: number | null;
  downloaded_size: number | null;
  speed: number | null;
  eta_seconds: number | null;
}

export interface FileRecord {
  id: number;
  download_id: number | null;
  path: string;
  filename: string;
  size: number | null;
  media_type: string | null;
  file_hash: string | null;
  duration: number | null;
  created_at: string;
  is_duplicate: number;
}

export interface Statistics {
  total: number;
  completed: number;
  failed: number;
  cancelled: number;
  active: number;
  queued: number;
  total_size: number;
  downloaded_size: number;
  storage_used: number;
  success_rate: number;
}

export interface SecurityEvent {
  id: number;
  event_type: string;
  severity: string;
  description: string;
  ip_address: string | null;
  url: string | null;
  created_at: string;
}

export interface Settings {
  max_concurrency: string;
  default_quality: string;
  default_format: string;
  subtitle_languages: string;
  auto_embed_subtitles: string;
  auto_organize: string;
  duplicate_detection: string;
  bandwidth_limit: string;
  save_location: string;
  notifications: string;
  retry_enabled: string;
  max_retries: string;
  embed_metadata: string;
  embed_thumbnail: string;
  theme: string;
  accent: string;
}

export interface DownloadCreatePayload {
  url: string;
  quality?: string;
  format?: string;
  subtitle_languages?: string[];
  save_location?: string;
}

export interface ApiResponse<T> {
  success?: boolean;
  error?: string;
  data?: T;
}
