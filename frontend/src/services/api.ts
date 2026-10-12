import type { FrameData, Session } from '@/lib/state';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { cache: 'no-store', ...options });
  } catch {
    throw new Error('Cannot reach the analysis server. Check that the backend is running on port 8000.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Analysis server returned ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export function startAnalysis(file: File, frameSkip: number, confidence: number, onProgress: (percent: number) => void): Promise<Session> {
  const data = new FormData();
  data.append('file', file);
  data.append('frame_skip', String(frameSkip));
  data.append('confidence', String(confidence));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/analysis');
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100));
    };
    xhr.onerror = () => reject(new Error('Cannot reach the analysis server. Check the backend on port 8000.'));
    xhr.onload = () => {
      let body;
      try { body = JSON.parse(xhr.responseText); } catch {
        const message = xhr.status === 413
          ? 'The video exceeds the upload size limit. Choose a file under 500 MB.'
          : xhr.status >= 200 && xhr.status < 300
            ? 'The upload server returned an unexpected response. Please retry.'
            : `Video upload failed (HTTP ${xhr.status}). Please retry; if it persists, check the frontend and backend logs.`;
        reject(new Error(message));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Session);
      else reject(new Error(typeof body.detail === 'string' ? body.detail : `Upload failed (${xhr.status}).`));
    };
    xhr.send(data);
  });
}

export const fetchSessions = () => request<Session[]>('/api/sessions');
export const fetchSession = (id: string) => request<Session>(`/api/sessions/${encodeURIComponent(id)}`);
export const fetchFrame = (id: string, index: number) => request<FrameData>(`/api/sessions/${encodeURIComponent(id)}/frames/${index}`);
export const cancelAnalysis = (id: string) => request<{ ok: boolean }>(`/api/sessions/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
export const checkBackend = () => request<{ ok: boolean; activeSession: string | null }>('/api/health');

