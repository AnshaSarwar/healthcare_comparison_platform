from uuid import uuid4

from backend.rag.generate import citations_from_answer
from backend.rag.loaders import strip_pricing_content
from backend.rag.rerank import _parse_order
from backend.rag.retriever import diversify_by_plan, record_key, reciprocal_rank_fusion


class TestStripPricingContent:
    def test_drops_pricing_section_and_premium_lines(self):
        text = """# Plan booklet

## Coverage
Maternity waiting period is 180 days.

## Pricing
| Band | Premium |
| 25-34 | 420 |

## Exclusions
Cosmetic surgery.

Confidential monthly premiums apply.
"""
        cleaned = strip_pricing_content(text)
        assert "Maternity waiting period" in cleaned
        assert "Cosmetic surgery" in cleaned
        assert "Pricing" not in cleaned
        assert "420" not in cleaned
        assert "Confidential monthly premiums" not in cleaned

    def test_keeps_premium_product_title_sections(self):
        text = """# MediCare Premium OPD+IPD

Pre-existing conditions are covered after 6 months.

## Pricing
| Band | Premium |
| 25-34 | 420 |
"""
        cleaned = strip_pricing_content(text)
        assert "6 months" in cleaned
        assert "MediCare Premium" in cleaned
        assert "420" not in cleaned

    def test_keeps_non_pricing_content(self):
        text = "## Waiting periods\n\nOPD waiting period is 30 days.\n"
        assert "30 days" in strip_pricing_content(text)


class TestReciprocalRankFusion:
    def test_merges_and_prefers_shared_top_hits(self):
        a = {
            "document_id": "d1",
            "parent_id": "p1",
            "chunk_index": 0,
            "text": "maternity",
        }
        b = {
            "document_id": "d1",
            "parent_id": "p2",
            "chunk_index": 0,
            "text": "exclusions",
        }
        c = {
            "document_id": "d2",
            "parent_id": "p3",
            "chunk_index": 0,
            "text": "network",
        }
        fused = reciprocal_rank_fusion([a, b], [c, a])
        assert record_key(fused[0]) == record_key(a)
        assert {record_key(item) for item in fused} == {
            record_key(a),
            record_key(b),
            record_key(c),
        }


class TestRerankParseOrder:
    def test_parses_json_order(self):
        assert _parse_order('{"order": [2, 0, 1]}', 3) == [2, 0, 1]

    def test_filters_out_of_range_and_falls_back_to_digits(self):
        assert _parse_order("best are 9 then 1 then 0", 3) == [1, 0]

    def test_handles_invalid_json_blob(self):
        assert _parse_order("{not-json} 1 0", 2) == [1, 0]


class TestCitationsFromAnswer:
    def test_maps_bracket_refs_to_records(self):
        plan_id = uuid4()
        doc_id = uuid4()
        records = [
            {
                "plan_id": str(plan_id),
                "document_id": str(doc_id),
                "plan_name": "HealthFirst",
                "section": "Maternity",
                "text": "Maternity waiting period is 180 days.",
            },
            {
                "plan_id": str(uuid4()),
                "document_id": str(uuid4()),
                "plan_name": "Other",
                "section": "Exclusions",
                "text": "Cosmetic surgery excluded.",
            },
        ]
        cites = citations_from_answer("Maternity wait is 180 days [1].", records)
        assert len(cites) == 1
        assert cites[0]["plan_name"] == "HealthFirst"
        assert cites[0]["section"] == "Maternity"
        assert "180 days" in cites[0]["quote"]

    def test_ignores_out_of_range_citations(self):
        records = [
            {
                "plan_id": str(uuid4()),
                "document_id": str(uuid4()),
                "plan_name": "A",
                "section": "Body",
                "text": "x",
            }
        ]
        assert citations_from_answer("See [2] and [0].", records) == []


class TestDiversifyByPlan:
    def test_ensures_one_hit_per_plan(self):
        plan_a = str(uuid4())
        plan_b = str(uuid4())
        plan_c = str(uuid4())
        records = [
            {"document_id": "d1", "parent_id": "p1", "chunk_index": 0, "plan_id": plan_a, "text": "a1"},
            {"document_id": "d1", "parent_id": "p2", "chunk_index": 0, "plan_id": plan_a, "text": "a2"},
            {"document_id": "d1", "parent_id": "p3", "chunk_index": 0, "plan_id": plan_a, "text": "a3"},
            {"document_id": "d2", "parent_id": "p4", "chunk_index": 0, "plan_id": plan_b, "text": "b1"},
            {"document_id": "d3", "parent_id": "p5", "chunk_index": 0, "plan_id": plan_c, "text": "c1"},
        ]
        picked = diversify_by_plan(records, plan_ids=[plan_a, plan_b, plan_c], k=3)
        assert [item["plan_id"] for item in picked] == [plan_a, plan_b, plan_c]

    def test_noop_for_single_plan(self):
        plan_a = str(uuid4())
        records = [
            {"document_id": "d1", "parent_id": "p1", "chunk_index": 0, "plan_id": plan_a},
            {"document_id": "d1", "parent_id": "p2", "chunk_index": 0, "plan_id": plan_a},
        ]
        picked = diversify_by_plan(records, plan_ids=[plan_a], k=1)
        assert len(picked) == 1
        assert picked[0]["parent_id"] == "p1"
