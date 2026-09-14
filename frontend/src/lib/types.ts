export type CoverageType = "opd" | "ipd" | "opd_ipd";
export type EligibilityOutcome = "pass" | "fail" | "partial";
export type ComparisonRequestStatus = "pending" | "completed" | "failed";
export type UserRole = "platform_admin" | "employer_admin" | "healthcare_org_admin";
export type OrganizationType = "employer" | "healthcare_provider";
export type PolicyReviewStatus =
  | "draft"
  | "needs_review"
  | "approved"
  | "archived"
  | "needs_correction"
  | "rejected";

export interface PlanTerms {
  waiting_period_days: number;
  exclusions: string[];
  sub_limits: Record<string, number>;
  maternity_coverage: boolean;
  maternity_waiting_days: number;
  pre_existing_condition_rules: string;
  min_employee_count: number;
}

export interface PricingTier {
  age_band_label: string;
  monthly_premium_per_employee: number;
}

export interface Plan {
  id: string;
  organization_id: string;
  provider_name: string;
  name: string;
  coverage_type: CoverageType;
  terms: PlanTerms;
  pricing_tiers: PricingTier[];
  network_hospital_count: number;
  source_document_id: string | null;
}

export interface PlanVersion {
  id: string;
  plan_id: string;
  version_label: string;
  coverage_type: CoverageType;
  effective_from: string | null;
  effective_to: string | null;
  review_status: PolicyReviewStatus;
  raw_terms: Record<string, unknown>;
  normalized_terms: PlanTerms;
  extraction_metadata: {
    method?: string;
    evidence?: { field: string; value: unknown; quote: string; confidence: number }[];
  };
  pricing_tiers: PricingTier[];
  source_document_id: string | null;
  imported_by_org_id: string | null;
  imported_by_role: UserRole | null;
  created_at: string;
}

export interface MeUser {
  id: string;
  email: string;
  role: UserRole;
  organization_id: string;
  organization_name: string;
  org_type: OrganizationType;
  email_verified: boolean;
}

export type ProviderInviteStatus = "pending" | "accepted" | "revoked" | "expired";

export interface ProviderInvite {
  id: string;
  email: string;
  organization_name: string;
  profile_name: string;
  status: ProviderInviteStatus;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface ProviderInvitePreview {
  email: string;
  organization_name: string;
  profile_name: string;
  expires_at: string;
}

export interface EmployerProfile {
  id: string;
  organization_id: string;
  name: string;
  demographics: {
    age_bands: { label: string; min_age: number; max_age: number; count: number }[];
    department_breakdown: Record<string, number>;
    total_dependents: number;
  };
  requirements: {
    budget_ceiling_per_employee: number;
    must_have_coverage_types: CoverageType[];
    min_headcount: number;
    maternity_required: boolean;
    pre_existing_coverage_required: boolean;
  };
}

export interface ProviderProfile {
  id: string;
  organization_id: string;
  name: string;
  hospital_count: number;
}

export interface Organization {
  id: string;
  name: string;
  org_type: OrganizationType;
}

export interface EligibilityRuleResult {
  rule_id: string;
  rule_name: string;
  outcome: EligibilityOutcome;
  message: string;
  details: Record<string, unknown>;
}

export interface PlanEligibilityResult {
  plan_id: string;
  plan_name: string;
  provider_organization_id: string;
  provider_name: string;
  overall_outcome: EligibilityOutcome;
  rules: EligibilityRuleResult[];
  estimated_monthly_cost: number | null;
  score_breakdown: Record<string, number>;
  total_score: number | null;
}

export interface Citation {
  plan_id: string;
  plan_name: string;
  section: string;
  quote: string;
  document_id: string;
  page_number: number | null;
}

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

export interface ComparisonResult {
  id: string;
  comparison_request_id: string;
  eligibility_matrix: PlanEligibilityResult[];
  scored_ranking: string[];
  narrative_explanation: string | null;
  citations: Citation[];
  audit_trace: Record<string, unknown>;
  created_at: string;
}

export interface ComparisonRequest {
  id: string;
  employer_organization_id: string;
  plan_ids: string[];
  status: ComparisonRequestStatus;
  result: ComparisonResult | null;
  created_at: string;
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
