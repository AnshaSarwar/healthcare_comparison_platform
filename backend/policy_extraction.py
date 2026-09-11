from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.enums import CoverageType
from backend.schemas.plan import PlanTerms


@dataclass(frozen=True)
class ExtractedPolicy:
    coverage_type: CoverageType
    terms: PlanTerms
    metadata: dict


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _number(text: str, pattern: str, default: int = 0) -> int:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else default


def _sub_limits(text: str) -> dict[str, float]:
    limits: dict[str, float] = {}
    for match in re.finditer(
        r"(?P<label>[A-Za-z][A-Za-z ]+?)\s+(?:is subject to a sub-limit of|is capped at)\s+(?P<value>[\d,]+)",
        text,
        re.IGNORECASE,
    ):
        limits[match.group("label").strip().lower().replace(" ", "_")] = float(
            match.group("value").replace(",", "")
        )
    return limits


def _evidence(field: str, value: object, text: str, confidence: float) -> dict:
    sentence = next(
        (part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if str(value).lower() in part.lower()),
        text[:240].strip(),
    )
    return {"field": field, "value": value, "quote": sentence[:500], "confidence": confidence}


def extract_policy_terms(text: str) -> ExtractedPolicy:
    coverage = _section(text, "Coverage overview")
    waiting = _section(text, "Waiting periods")
    maternity = _section(text, "Maternity coverage")
    pre_existing = _section(text, "Pre-existing conditions")
    exclusions_text = _section(text, "Exclusions")
    limits = _section(text, "Sub-limits and ancillary benefits")
    group_rules = _section(text, "Claims and group rules")

    if re.search(r"inpatient-only|IPD only", coverage, re.IGNORECASE):
        coverage_type = CoverageType.IPD
    elif re.search(r"combined outpatient.*inpatient|OPD\+IPD", coverage, re.IGNORECASE):
        coverage_type = CoverageType.OPD_IPD
    elif re.search(r"outpatient|OPD", coverage, re.IGNORECASE) and not re.search(r"inpatient.*only|IPD", coverage, re.IGNORECASE):
        coverage_type = CoverageType.OPD
    else:
        coverage_type = CoverageType.IPD

    maternity_coverage = bool(
        re.search(r"maternity coverage is included", maternity, re.IGNORECASE)
    ) and not bool(re.search(r"maternity coverage is not included", maternity, re.IGNORECASE))
    maternity_waiting_days = _number(maternity, r"waiting period of\s+(\d+)\s+days", 0)
    waiting_period_days = _number(waiting, r"waiting period of\s+(\d+)\s+days", 0)
    min_employee_count = _number(
        f"{coverage}\n{group_rules}",
        r"(?:minimum group size|minimum employee count|at least)(?:\s+is)?\s+(\d+)",
        1,
    )
    pre_existing_rules = pre_existing if pre_existing else ""
    exclusion_items = [item.strip(" .") for item in re.split(r":|;", exclusions_text, maxsplit=1)[-1].split(",") if item.strip()]

    terms = PlanTerms(
        waiting_period_days=waiting_period_days,
        exclusions=exclusion_items,
        sub_limits=_sub_limits(limits),
        maternity_coverage=maternity_coverage,
        maternity_waiting_days=maternity_waiting_days,
        pre_existing_condition_rules=pre_existing_rules,
        min_employee_count=min_employee_count,
    )
    evidence = [
        _evidence("coverage_type", coverage_type.value, coverage, 0.95),
        _evidence("waiting_period_days", waiting_period_days, waiting, 0.9),
        _evidence("maternity_coverage", maternity_coverage, maternity, 0.95),
        _evidence("maternity_waiting_days", maternity_waiting_days, maternity, 0.9),
        _evidence("pre_existing_condition_rules", pre_existing_rules, pre_existing, 0.85),
        _evidence("min_employee_count", min_employee_count, group_rules, 0.9),
    ]
    return ExtractedPolicy(
        coverage_type=coverage_type,
        terms=terms,
        metadata={"method": "deterministic_section_extractor_v1", "evidence": evidence},
    )
