// Typed client for every endpoint in TRD.md §16. The frontend talks to the backend only through this module.
import type {
  SecurityAlert, TelegramStatus,
  DeliveryStatus, DemoState, DraftTestResult, EventDetail, EventSummary, Health, IncidentDetail, IncidentSummary, IncidentWorkflow,
  LedgerBatch, LedgerVerifyResult, ParquetExport, ParserDraft, ParserInfo, QuarantineGroup, RecordVerifyResult,
  RetentionReport, SearchResult, SourceInfo, Stats, TamperInfo, WitnessInfo,
} from './types';

const BASE = '/api';

export interface Session {
  enabled: boolean; authenticated: boolean; username: string | null;
  multi_user?: boolean; role?: string | null; account_id?: string | null;
  public_signup?: boolean;
  terms_version?: string; terms_accepted?: boolean;
}
export interface LegalNotice {
  version: string; operator: string; contact: string;
  terms: { title: string; text: string }[]; privacy: { title: string; text: string }[];
}

export interface AIStatus { configured: boolean; evidence_enabled: boolean; provider: string; model: string | null }
export interface AIExplanationResult {
  claims: { text: string; citations: string[] }[]; steps: string[];
  references: Record<string, { label: string; href: string }>;
  model: string; sample_count: number; returned_count: number; truncated: boolean;
}
export interface AIPreview {
  preview_id: string;
  context: Record<string, unknown>; evidence: { id: string; fields: Record<string, unknown> }[];
  returned_count: number; sample_count: number; truncated: boolean; note: string;
}

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
  alerts: {
    list: (before?: number) => get<{ items: SecurityAlert[]; unread: number; next_before: number | null }>('/alerts', { before }),
    acknowledge: (id: number) => post<{ ok: boolean }>(`/alerts/${id}/acknowledge`),
    telegram: () => get<TelegramStatus>('/notifications/telegram'),
    configure: (bot_token: string, chat_id: string, consent: boolean) => post<TelegramStatus>('/notifications/telegram', { bot_token, chat_id, consent }),
    disable: () => post<TelegramStatus>('/notifications/telegram/disable'),
    test: () => post<{ ok: boolean }>('/notifications/telegram/test'),
  },
  auth: {
    session: () => get<Session>('/auth/session'),
    login: (username: string, password: string) => post<{ ok: boolean }>('/auth/login', { username, password }),
    logout: () => post<{ ok: boolean }>('/auth/logout'),
    register: (invite: string, username: string, password: string, terms_version: string) =>
      post<{ ok: boolean; recovery_code: string }>('/auth/register', { invite, username, password, terms_version }),
    recoveryOptions: () => get<{ code_available: boolean }>('/auth/recovery-options'),
    resetPassword: (body: { username: string; code: string; password: string }) => post<{ ok: boolean }>('/auth/reset-password', body),
    acceptTerms: (terms_version: string) => post<{ ok: boolean }>('/auth/accept-terms', { terms_version }),
  },
  legal: () => get<LegalNotice>('/legal'),
  account: {
    profile: () => get<{ username: string; role: string; account_id: string; has_collector_key: boolean; terms_version: string; accepted_at: number; origin: string; raw_limit_bytes: number; has_recovery_code: boolean }>('/account'),
    recoveryCode: (password: string) => post<{ code: string }>('/account/recovery-code', { password }),
    rotateKey: () => post<{ key: string }>('/account/collector-key'),
    list: () => get<{ items: { id: string; username: string; role: string; disabled: number }[]; invitations: { id: string; expires_at: number }[]; limit: number }>('/admin/accounts'),
    invite: () => post<{ url: string; expires_at: number }>('/admin/invites'),
    revoke: (id: string) => post<{ ok: boolean }>(`/admin/invites/${id}/revoke`),
    disable: (id: string) => post<{ ok: boolean }>(`/admin/accounts/${id}/disable`),
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
    blockPlan: (id: string, device: string, minutes: 5 | 15) => post<{ version: number; plan_id: string; device: string; source_ip: string; minutes: number; created_at: number; expires_at: number; action: string; incident_id: string }>(`/incidents/${id}/block-plan`, { device, minutes }),
    list: () => get<{ items: IncidentSummary[] }>('/incidents'),
    get: (id: string) => get<IncidentDetail>(`/incidents/${id}`),
    investigate: (id: string, body: IncidentWorkflow & { note: string }) => post<IncidentDetail>(`/incidents/${id}/investigation`, body),
    report: async (id: string, verify: boolean): Promise<Blob> => {
      const response = await fetch(`${BASE}/incidents/${encodeURIComponent(id)}/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Anvaya-Request': 'console' },
        body: JSON.stringify({ verify }),
      });
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event('anvaya:unauthorized'));
        const error = await response.json().catch(() => null);
        throw new ApiError(response.status, error?.error?.code ?? 'http_error',
          error?.error?.message ?? 'Could not generate the report. Please retry.');
      }
      return response.blob();
    },
  },
  search: {
    ask: (question: string, options: { use_ai?: boolean; consent?: boolean; previous_id?: string } = {}) => post<SearchResult>('/search', { question, ...options }),
    suggestions: () => get<{ items: string[] }>('/search/suggestions'),
  },
  ai: {
    status: () => get<AIStatus>('/ai/status'),
    preview: (kind: 'search' | 'incident', target: string) => post<AIPreview>('/ai/preview', { kind, target }),
    explain: (kind: 'search' | 'incident', target: string, consent: boolean, preview_id: string) => post<AIExplanationResult>('/ai/explain', { kind, target, consent, preview_id }),
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
