from enum import StrEnum


class OrganizationType(StrEnum):
    EMPLOYER = "employer"
    HEALTHCARE_PROVIDER = "healthcare_provider"


class UserRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    EMPLOYER_ADMIN = "employer_admin"
    HEALTHCARE_ORG_ADMIN = "healthcare_org_admin"


class CoverageType(StrEnum):
    OPD = "opd"
    IPD = "ipd"
    OPD_IPD = "opd_ipd"


class ComparisonRequestStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EligibilityOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class DocumentIndexStatus(StrEnum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"


class PolicyReviewStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    NEEDS_CORRECTION = "needs_correction"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"
