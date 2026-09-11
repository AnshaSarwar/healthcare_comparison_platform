import { clearToken, getToken } from "./auth";
import type {
  AgentSseEvent,
  ComparisonRequest,
  EmployerProfile,
  MeUser,
  Organization,
  OrganizationType,
  Plan,
  PlanTerms,
  PricingTier,
  ProviderProfile,
  CoverageType,
  PlanVersion,
  PolicyReviewStatus,
} from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8102";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (!token) {
      throw new ApiError("Not authenticated", 401);
    }
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) {
        detail = body.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ");
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>(
    "/api/v1/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    },
    false,
  );
  return data.access_token;
}

export async function register(body: {
  email: string;
  password: string;
  organization_name: string;
  org_type: OrganizationType;
  profile_name: string;
}): Promise<string> {
  const data = await request<{ access_token: string }>(
    "/api/v1/auth/register",
    { method: "POST", body: JSON.stringify(body) },
    false,
  );
  return data.access_token;
}

export async function fetchMe(): Promise<MeUser> {
  return request<MeUser>("/api/v1/auth/me");
}

export async function getEmployerMe(): Promise<EmployerProfile> {
  return request<EmployerProfile>("/api/v1/employers/me");
}

export async function updateEmployerMe(
  body: Partial<Pick<EmployerProfile, "name" | "demographics" | "requirements">>,
): Promise<EmployerProfile> {
  return request<EmployerProfile>("/api/v1/employers/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function getProviderMe(): Promise<ProviderProfile> {
  return request<ProviderProfile>("/api/v1/providers/me");
}

export async function addHospital(body: {
  name: string;
  city: string;
  tier?: string;
}): Promise<{ id: string; name: string; city: string; tier: string }> {
  return request("/api/v1/providers/me/hospitals", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createPlan(body: {
  name: string;
  coverage_type: CoverageType;
  terms: PlanTerms;
  pricing_tiers: PricingTier[];
}): Promise<Plan> {
  return request<Plan>("/api/v1/plans", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updatePlan(
  planId: string,
  body: {
    name?: string;
    coverage_type?: CoverageType;
    terms?: PlanTerms;
    pricing_tiers?: PricingTier[];
  },
): Promise<Plan> {
  return request<Plan>(`/api/v1/plans/${planId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function listPlanVersions(planId: string): Promise<PlanVersion[]> {
  return request<PlanVersion[]>(`/api/v1/plans/${planId}/versions`);
}

export async function reviewPlanVersion(
  versionId: string,
  review_status: PolicyReviewStatus,
  review_notes?: string,
): Promise<PlanVersion> {
  return request<PlanVersion>(`/api/v1/plan-versions/${versionId}/review`, {
    method: "PATCH",
    body: JSON.stringify({ review_status, review_notes }),
  });
}

export async function fetchDocumentContent(documentId: string): Promise<Blob> {
  const token = getToken();
  if (!token) throw new ApiError("Not authenticated", 401);
  const res = await fetch(`${API_URL}/api/v1/documents/${documentId}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new ApiError("Unable to load source document", res.status);
  return res.blob();
}

export async function listOrganizations(): Promise<Organization[]> {
  return request<Organization[]>("/api/v1/organizations");
}

export async function createOrganization(body: {
  name: string;
  org_type: OrganizationType;
  profile_name: string;
}): Promise<Organization> {
  return request<Organization>("/api/v1/organizations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createUser(body: {
  email: string;
  password: string;
  role: string;
  organization_id: string;
}): Promise<{ id: string; email: string; role: string }> {
  return request("/api/v1/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listPlans(): Promise<Plan[]> {
  return request<Plan[]>("/api/v1/plans");
}

export async function createComparison(planIds: string[]): Promise<ComparisonRequest> {
  return request<ComparisonRequest>("/api/v1/comparisons", {
    method: "POST",
    body: JSON.stringify({ plan_ids: planIds }),
  });
}

export async function getComparison(id: string): Promise<ComparisonRequest> {
  return request<ComparisonRequest>(`/api/v1/comparisons/${id}`);
}

export async function streamAgentChat(
  body: { question: string; plan_ids?: string[]; thread_id?: string | null },
  onEvent: (event: AgentSseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  if (!token) throw new ApiError("Not authenticated", 401);

  const res = await fetch(`${API_URL}/api/v1/agents/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      question: body.question,
      plan_ids: body.plan_ids || [],
      thread_id: body.thread_id || null,
    }),
    signal,
  });

  if (res.status === 401) {
    clearToken();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = await res.json();
      if (typeof errBody?.detail === "string") detail = errBody.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new ApiError("No response stream", 500);

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("data:"));
      if (!line) continue;
      const raw = line.slice(5).trim();
      if (!raw) continue;
      try {
        onEvent(JSON.parse(raw) as AgentSseEvent);
      } catch {
        /* skip malformed chunk */
      }
    }
  }
}

export { ApiError };
