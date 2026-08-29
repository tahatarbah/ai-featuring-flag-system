export type Variant = { id: string; key: string; is_control: boolean; payload: Record<string, unknown> };
export type Rule = {
  id: string;
  priority: number;
  attribute: string;
  op: string;
  value: string;
  variant_id: string;
  variant_key: string;
};
export type SLO = {
  id: string;
  metric: string;
  comparator: string;
  threshold: number;
  min_samples: number;
  action: string;
};
export type Flag = {
  id: string;
  key: string;
  name: string;
  description: string;
  flag_type: string;
  status: string;
  kill_switch: boolean;
  salt: string;
  archived: boolean;
  variants: Variant[];
  rules: Rule[];
  rollout: { percentage_bps: number; stage: number; auto_advance: boolean; last_action_at: string | null } | null;
  slos: SLO[];
};
export type Quality = {
  flag_key: string;
  window_minutes: number;
  control: Arm | null;
  treatment: Arm | null;
  last_decision: {
    id: string;
    action: string;
    reason: string;
    metrics: Record<string, unknown>;
    ts: string;
  } | null;
};
export type Arm = {
  variant_key: string;
  samples: number;
  error_rate: number;
  latency_p95: number;
  judge_mean: number;
  tokens_per_request: number;
  judge_samples: number;
};
export type Audit = {
  id: string;
  actor: string;
  action: string;
  flag_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ts: string;
};
export type AskResult = {
  answer: string;
  evaluation: {
    flag_key: string;
    variant_key: string;
    payload: Record<string, unknown>;
    reason: string;
    bucket: number | null;
  };
  confidence_shown: boolean;
  judge_score: number | null;
  judge_reason: string;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  error_code: string | null;
  model: string;
};
export type SystemStatus = {
  status: string;
  database: string;
  ollama: string;
  demo_mock_llm: boolean;
  gate_enabled: boolean;
  gate_window_minutes: number;
  flag_count: number;
  active_flags: number;
  impressions_15m: number;
  generations_15m: number;
  quality_events_15m: number;
  last_gate_action: string | null;
  last_gate_reason: string | null;
};
export type Overview = {
  flags: {
    id: string;
    key: string;
    name: string;
    status: string;
    kill_switch: boolean;
    percentage_bps: number;
    auto_advance: boolean;
    variant_count: number;
  }[];
  recent_audit: { id: string; actor: string; action: string; ts: string | null; after: Record<string, unknown> | null }[];
};
export type EvalResult = {
  flag_key: string;
  variant_key: string;
  payload: Record<string, unknown>;
  reason: string;
  bucket: number | null;
};
export type GateDecision = {
  id: string;
  flag_id: string;
  flag_key: string;
  action: string;
  reason: string;
  metrics: Record<string, unknown>;
  ts: string | null;
};

const TOKEN_KEY = "warden_admin_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${getToken()}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  overview: () => req<Overview>("/api/v1/overview"),
  status: () => req<SystemStatus>("/api/v1/system/status"),
  flags: () => req<Flag[]>("/api/v1/flags"),
  flag: (id: string) => req<Flag>(`/api/v1/flags/${id}`),
  createFlag: (body: Record<string, unknown>) =>
    req<Flag>("/api/v1/flags", { method: "POST", body: JSON.stringify(body) }),
  patchFlag: (id: string, body: Record<string, unknown>) =>
    req<Flag>(`/api/v1/flags/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  publish: (id: string) => req<Flag>(`/api/v1/flags/${id}/publish`, { method: "POST" }),
  pause: (id: string) => req<Flag>(`/api/v1/flags/${id}/pause`, { method: "POST" }),
  kill: (id: string) => req<Flag>(`/api/v1/flags/${id}/kill`, { method: "POST" }),
  restore: (id: string) => req<Flag>(`/api/v1/flags/${id}/restore`, { method: "POST" }),
  advance: (id: string) => req<Flag>(`/api/v1/flags/${id}/advance`, { method: "POST" }),
  setRules: (id: string, rules: { priority: number; attribute: string; op: string; value: string; variant_key: string }[]) =>
    req<Flag>(`/api/v1/flags/${id}/rules`, { method: "PUT", body: JSON.stringify(rules) }),
  setSlos: (id: string, slos: { metric: string; comparator: string; threshold: number; min_samples: number; action: string }[]) =>
    req<Flag>(`/api/v1/flags/${id}/slos`, { method: "PUT", body: JSON.stringify(slos) }),
  quality: (id: string) => req<Quality>(`/api/v1/flags/${id}/quality`),
  audit: () => req<Audit[]>("/api/v1/audit"),
  gateDecisions: () => req<GateDecision[]>("/api/v1/gate-decisions"),
  evaluate: (flag_key: string, user_key: string, attributes: Record<string, string> = {}) =>
    req<EvalResult>("/api/v1/evaluate", {
      method: "POST",
      body: JSON.stringify({ flag_key, user_key, attributes }),
    }),
  ask: (user_key: string, question: string) =>
    req<AskResult>("/api/v1/demo/ask", { method: "POST", body: JSON.stringify({ user_key, question }) }),
  simulate: (users: number, question?: string) =>
    req<{ asked: number; variants: Record<string, number>; errors: number; avg_judge: number | null }>(
      "/api/v1/demo/simulate",
      { method: "POST", body: JSON.stringify({ users, question }) },
    ),
  thumbs: (payload: { user_key: string; variant_key: string; score: number; flag_key?: string }) =>
    req<{ status: string }>("/api/v1/demo/thumbs", { method: "POST", body: JSON.stringify(payload) }),
};
