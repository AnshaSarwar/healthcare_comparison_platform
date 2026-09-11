from pathlib import Path

from backend.domain.enums import CoverageType
from backend.policy_extraction import extract_policy_terms


ROOT = Path(__file__).resolve().parents[1]


def test_extracts_healthfirst_comparison_terms() -> None:
    text = (ROOT / "data" / "plans" / "healthfirst_corporate_opd_ipd.md").read_text()
    extracted = extract_policy_terms(text)

    assert extracted.coverage_type == CoverageType.OPD_IPD
    assert extracted.terms.waiting_period_days == 30
    assert extracted.terms.maternity_coverage is True
    assert extracted.terms.maternity_waiting_days == 180
    assert extracted.terms.min_employee_count == 25
    assert extracted.terms.pre_existing_condition_rules
    assert extracted.metadata["method"] == "deterministic_section_extractor_v1"
    assert len(extracted.metadata["evidence"]) >= 5


def test_extracts_absent_maternity_and_ipd_only() -> None:
    text = (ROOT / "data" / "plans" / "medicare_essential_ipd.md").read_text()
    extracted = extract_policy_terms(text)

    assert extracted.coverage_type == CoverageType.IPD
    assert extracted.terms.waiting_period_days == 60
    assert extracted.terms.maternity_coverage is False
    assert extracted.terms.maternity_waiting_days == 0
    assert extracted.terms.min_employee_count == 50
