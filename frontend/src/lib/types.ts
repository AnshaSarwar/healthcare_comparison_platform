import type { components } from "./generated-types";

type Schemas = components["schemas"];

// Enums / literal unions -- derived from the backend's Pydantic enums.
export type CoverageType = Schemas["CoverageType"];
export type EligibilityOutcome = Schemas["EligibilityOutcome"];
export type ComparisonRequestStatus = Schemas["ComparisonRequestStatus"];
export type UserRole = Schemas["UserRole"];
export type OrganizationType = Schemas["OrganizationType"];
export type PolicyReviewStatus = Schemas["PolicyReviewStatus"];

// Nested value objects.
export type PlanTerms = Schemas["PlanTerms"];
export type PricingTier = Schemas["PricingTier"];
export type AgeBand = Schemas["AgeBand"];
export type EmployeeDemographics = Schemas["EmployeeDemographics"];
export type EmployerRequirements = Schemas["EmployerRequirements"];

// Top-level resources returned by REST endpoints.
export type Plan = Schemas["PlanRead"];

// `PlanVersionRead.extraction_metadata` is an untyped `dict` on the backend
// (same as `raw_terms`), so the generated schema only gives it an index
// signature. Narrow it here to the shape backend/services/document.py
// actually populates it with.
export type PlanVersion = Omit<Schemas["PlanVersionRead"], "extraction_metadata"> & {
  extraction_metadata: {
    method?: string;
    evidence?: { field: string; value: unknown; quote: string; confidence: number }[];
  };
};
export type MeUser = Schemas["MeResponse"];
export type EmployerProfile = Schemas["EmployerRead"];
export type ProviderProfile = Schemas["ProviderRead"];
export type Organization = Schemas["OrganizationRead"];
export type EligibilityRuleResult = Schemas["EligibilityRuleResult"];
export type PlanEligibilityResult = Schemas["PlanEligibilityResult"];
export type Citation = Schemas["Citation"];
export type ComparisonResult = Schemas["ComparisonResultRead"];
export type ComparisonRequest = Schemas["ComparisonRequestRead"];
export type ProviderInvitePreview = Schemas["ProviderInvitePreview"];

// `ProviderInviteRead.status` is typed as a plain `str` on the backend (its
// values come from a DB check constraint, not a Pydantic enum), so it isn't
// narrowed in the generated schema. Narrow it here from the known values.
export type ProviderInviteStatus = "pending" | "accepted" | "revoked" | "expired";
export type ProviderInvite = Omit<Schemas["ProviderInviteRead"], "status"> & {
  status: ProviderInviteStatus;
};

// --- Frontend-only types -----------------------------------------------
// `/agents/chat` and `/rag/query` stream Server-Sent Events and declare no
// `response_model` (there's nothing static for FastAPI to introspect), so
// their event shapes can't be derived from the OpenAPI schema and stay
// hand-written here, kept in sync with backend/api/v1/agents.py by hand.

export interface SourceChunk {
  index: number;
  plan_id: string | null;
  plan_name: string | null;
  section: string | null;
  document_id: string | null;
  chunk_index: number | null;
  page_number: number | null;
  score: number | null;
}

export interface AgentChatFinal {
  type: "final";
  answer: string;
  citations: Citation[];
  route: string;
  trace: { node: string; detail: string }[];
  comparison_summary: Record<string, unknown> | null;
  thread_id: string | null;
}

export type AgentSseEvent =
  | { type: "token"; text: string }
  | { type: "sources"; sources: SourceChunk[] }
  | { type: "step"; node: string; detail: string }
  | { type: "error"; detail: string }
  | AgentChatFinal;
