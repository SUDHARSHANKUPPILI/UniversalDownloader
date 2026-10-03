import type { Settings } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(err.error || `HTTP ${response.status}`);
  }
  return response.json();
}

export const api = {
  // Health
  health: () => request<{ status: string; service: string }>('/api/v1/health'),

  // URL Analysis
  analyzeUrl: (url: string) =>
    request<{ valid: boolean; error?: string; title?: string }>('/api/v1/analyze', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),

  // Downloads
  createDownload: (payload: { url: string; quality?: string; format?: string; subtitle_languages?: string[]; save_location?: string }) =>
    request<{ success: boolean; download_id: number; title: string; is_duplicate: boolean }>('/api/v1/download', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getDownloads: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ downloads: any[]; page: number; per_page: number }>(`/api/v1/downloads?${q}`);
  },
  getDownload: (id: number) => request<{ id: number }>(`/api/v1/download/${id}`),
  pauseDownload: (id: number) => request<{ success: boolean }>(`/api/v1/download/${id}/pause`, { method: 'POST' }),
  resumeDownload: (id: number) => request<{ success: boolean }>(`/api/v1/download/${id}/resume`, { method: 'POST' }),
  cancelDownload: (id: number) => request<{ success: boolean }>(`/api/v1/download/${id}/cancel`, { method: 'POST' }),
  retryDownload: (id: number) => request<{ success: boolean }>(`/api/v1/download/${id}/retry`, { method: 'POST' }),
  removeDownload: (id: number) => request<{ success: boolean }>(`/api/v1/download/${id}`, { method: 'DELETE' }),

  // Queue
  getQueue: () => request<{ queue: any[] }>('/api/v1/queue'),
  reorderQueue: (items: { id: number }[]) =>
    request<{ success: boolean }>('/api/v1/queue/reorder', {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),

  // History
  getHistory: (limit = 50, offset = 0, statusFilter?: string) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (statusFilter) params.set('status', statusFilter);
    return request<{ history: any[]; limit: number; offset: number }>(`/api/v1/history?${params}`);
  },

  // Files
  getFiles: () => request<{ files: any[] }>('/api/v1/files'),
  deleteFile: (id: number) => request<{ success: boolean }>(`/api/v1/files/${id}`, { method: 'DELETE' }),
  openFile: (id: number) => request<{ success: boolean }>(`/api/v1/files/${id}/open`, { method: 'POST' }),
  revealFile: (id: number) => request<{ success: boolean }>(`/api/v1/files/${id}/reveal`, { method: 'POST' }),

  // Statistics
  getStatistics: () => request<{ total: number; completed: number; failed: number; cancelled: number; active: number; queued: number; total_size: number; downloaded_size: number; storage_used: number; success_rate: number }>('/api/v1/statistics'),

  // Analytics
  getAnalytics: () => request<{ daily: any[]; monthly: any[]; total_downloads: number; total_size: number }>('/api/v1/analytics'),

  // Subtitles
  getSubtitles: () => request<{ subtitles: any[] }>('/api/v1/subtitles'),
  deleteSubtitle: (id: number) => request<{ success: boolean }>(`/api/v1/subtitles/${id}`, { method: 'DELETE' }),

  // Settings
  getSettings: () => request<Settings>('/api/v1/settings'),
  updateSettings: (settings: Settings) =>
    request<{ success: boolean }>('/api/v1/settings', { method: 'PUT', body: JSON.stringify(settings) }),

  // Security
  getSecurityEvents: (limit = 50) => request<{ id: number }[]>(`/api/v1/security/events?limit=${limit}`),
  getNetworkInfo: () => request<{ hostname: string; local_ip: string }>('/api/v1/network'),
  getDuplicates: () => request<{ duplicates: any[] }>('/api/v1/duplicates'),
};
