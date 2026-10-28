// 대시보드는 upload 호스트에서 같은 오리진 /api/v1 을 쓰고,
// 공개 목록(science26.bssm.dev)은 쿠키 없이 upload 호스트의 /public 만 부른다.
export const UPLOAD_HOST = process.env.EXPO_PUBLIC_UPLOAD_HOST || 'science26-upload.bssm.dev';
export const PUBLIC_HOST = process.env.EXPO_PUBLIC_PUBLIC_HOST || 'science26.bssm.dev';

const isPublicHost = () =>
  typeof window !== 'undefined' &&
  (window.location.hostname === PUBLIC_HOST || window.location.search.includes('public=1'));

export const API_BASE = isPublicHost() ? `https://${UPLOAD_HOST}/api/v1` : '/api/v1';
export { isPublicHost };

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public detail?: unknown) {
    super(message);
  }
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  // 서버의 CSRF 검사용. 다른 출처(학생 페이지)는 이 헤더를 붙이면 CORS 사전 요청에서 막힌다.
  if (init.method && init.method !== 'GET') headers['X-S26-Request'] = '1';
  const res = await fetch(API_BASE + path, {
    ...init,
    headers,
    credentials: isPublicHost() ? 'omit' : 'same-origin',
  });
  if (!res.ok) {
    let body: any = {};
    try {
      body = await res.json();
    } catch {}
    throw new ApiError(res.status, body.code || 'ERROR', body.message || `요청 실패 (${res.status})`, body.detail);
  }
  return res.json();
}

export const json = (data: unknown): RequestInit => ({ body: JSON.stringify(data) });

export type Me = { email: string; name: string; role: 'student' | 'admin'; student_no: string | null; mapped: boolean };

export type ReleaseState = 'queued' | 'validating' | 'building' | 'deploying' | 'active' | 'failed' | 'superseded';
export type Release = {
  id: string;
  version: number;
  type: ProjectType;
  source_kind: string;
  source_ref: string;
  state: ReleaseState;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};
export type ProjectType = 'static' | 'fullstack' | 'app';
export type ProjectStatus = 'empty' | 'building' | 'running' | 'sleeping' | 'stopped' | 'failed';
export type Project = {
  visits?: { total: number; today: number };
  student_no: string;
  slug: string;
  type: ProjectType | null;
  title: string;
  description: string;
  thumbnail_url: string | null;
  listed: boolean;
  status: ProjectStatus;
  url: string | null;
  last_request_at: string | null;
  active_release: Release | null;
  latest_release: Release | null;
};
export type PublicCard = {
  student_no: string;
  slug: string;
  name: string;
  title: string;
  description: string;
  type: ProjectType;
  status: ProjectStatus;
  thumbnail_url: string | null;
  url: string;
  views?: number;
  hot?: number;
  updated_at?: string;
};
export type Warning = { code: string; message: string; paths?: string[] };
