// Typed client for every endpoint in TRD.md §16. The frontend talks to the backend only through this module.
import type {
  DeliveryStatus, DemoState, DraftTestResult, EventDetail, EventSummary, Health, IncidentDetail, IncidentSummary,
  LedgerBatch, LedgerVerifyResult, ParquetExport, ParserDraft, ParserInfo, QuarantineGroup, RecordVerifyResult,
  RetentionReport, SearchResult, SourceInfo, Stats, TamperInfo, WitnessInfo,
} from './types';

const BASE = '/api';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public detail: Record<string, unknown> = {}) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
  const qs = params
    ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))
    : '';
  let res: Response;
  try {
    res = await fetch(BASE + path + qs, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json', 'X-Anvaya-Request': 'console' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network', 'Network error');
  }
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('anvaya:unauthorized'));
    const err = await res.json().catch(() => null);
    throw new ApiError(res.status, err?.error?.code ?? 'http_error', err?.error?.message ?? res.statusText,
      err?.error?.detail ?? {});
  }
  return (await res.json()) as T;
}

const get = <T>(path: string, params?: Record<string, unknown>) => request<T>('GET', path, undefined, params);
const post = <T>(path: string, body: unknown = {}) => request<T>('POST', path, body);

export const api = {
  auth: {
    session: () => get<{ enabled: boolean; authenticated: boolean; username: string | null }>('/auth/session'),
    login: (username: string, password: string) => post<{ ok: boolean }>('/auth/login', { username, password }),
    logout: () => post<{ ok: boolean }>('/auth/logout'),
  },
  health: () => get<Health>('/health'),
  stats: () => get<Stats>('/stats'),
  ingest: (lines: string[]) => post<{ accepted: number; raw_ids: string[]; flagged: number }>('/ingest', { lines }),
  events: {
    list: (p: { limit?: number; before_seq?: number; device?: string; format?: string; class_uid?: number; q?: string } = {}) =>
      get<{ items: EventSummary[]; next_before_seq: number | null }>('/events', p),
    get: (eventId: string) => get<EventDetail>(`/events/${eventId}`),
  },
  rawUrl: (rawId: string) => `${BASE}/raw/${rawId}`,
  ledger: {
    verifyRecord: (rawId: string) => post<RecordVerifyResult>(`/ledger/verify/${rawId}`),
    batches: (p: { limit?: number; before_batch?: number } = {}) =>
      get<{ items: LedgerBatch[]; primary_key_fingerprint: string }>('/ledger/batches', p),
    verify: () => post<LedgerVerifyResult>('/ledger/verify'),
  },
  witnesses: () => get<{ items: WitnessInfo[] }>('/witnesses'),
  sources: () => get<{ items: SourceInfo[] }>('/sources'),
  quarantine: () => get<{ total: number; groups: QuarantineGroup[] }>('/quarantine'),
  replay: (body: { group_id: string } | { raw_ids: string[] }) => post<{ replay_id: string; queued: number }>('/replay', body),
  parsers: {
    list: () => get<{ items: ParserInfo[] }>('/parsers'),
    draft: (groupId: string) => post<ParserDraft>('/parsers/drafts', { group_id: groupId }),
    getDraft: (draftId: string) => get<ParserDraft>(`/parsers/drafts/${draftId}`),
    test: (draftId: string) => post<DraftTestResult>(`/parsers/drafts/${draftId}/test`),
    approve: (draftId: string, approvedBy = 'analyst@ntro-demo') =>
      post<{ parser: { name: string; version: string; status: string }; replay_id: string; queued: number }>(
        `/parsers/drafts/${draftId}/approve`, { approved_by: approvedBy }),
    reject: (draftId: string, reason: string) =>
      post<{ draft_id: string; status: string }>(`/parsers/drafts/${draftId}/reject`, { reason }),
  },
  incidents: {
    list: () => get<{ items: IncidentSummary[] }>('/incidents'),
    get: (id: string) => get<IncidentDetail>(`/incidents/${id}`),
  },
  search: {
    ask: (question: string) => post<SearchResult>('/search', { question }),
    suggestions: () => get<{ items: string[] }>('/search/suggestions'),
  },
  delivery: {
    status: () => get<DeliveryStatus>('/delivery/status'),
    exportParquet: (body: { from_ms?: number | null; to_ms?: number | null } = {}) =>
      post<ParquetExport>('/export/parquet', { from_ms: null, to_ms: null, ...body }),
    retention: () => get<RetentionReport>('/reports/retention'),
  },
  demo: {
    state: () => get<DemoState>('/demo/state'),
    reset: () => post<{ ok: boolean; took_ms: number }>('/demo/reset'),
    start: (speed?: number) => post<{ phase: string; speed: number; scripted_lines: number }>('/demo/scenario/start', { speed }),
    injectUnknown: () => post<{ lines: number }>('/demo/inject-unknown'),
    silence: (device: string, silent: boolean) => post<{ device: string; silent: boolean }>('/demo/silence', { device, silent }),
    tamper: () => post<TamperInfo>('/demo/tamper'),
    reseal: () => post<{ resealed_batches: number[]; note: string }>('/demo/reseal'),
    speed: (speed: number) => post<{ speed: number }>('/demo/speed', { speed }),
  },
};
