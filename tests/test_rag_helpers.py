from uuid import uuid4

from backend.rag.generate import citations_from_answer, sources_from_records
from backend.rag.layout import extract_blocks
from backend.rag.loaders import strip_pricing_content
from backend.rag.rerank import _parse_order, rerank_pairwise
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


class TestExtractBlocks:
    def test_pure_prose_is_a_single_block(self):
        text = "Maternity waiting period is 180 days.\nCosmetic surgery is excluded.\n"
        blocks = extract_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "prose"
        assert "180 days" in blocks[0]["text"]

    def test_pipe_table_is_kept_as_one_table_block(self):
        text = (
            "## Pricing\n"
            "| Band | Premium |\n"
            "| --- | --- |\n"
            "| 25-34 | 420 |\n"
            "| 35-44 | 480 |\n"
            "\nExclusions apply.\n"
        )
        blocks = extract_blocks(text)
        table_blocks = [b for b in blocks if b["type"] == "table"]
        assert len(table_blocks) == 1
        assert "| 25-34 | 420 |" in table_blocks[0]["text"]
        assert "| 35-44 | 480 |" in table_blocks[0]["text"]
        # The table isn't fragmented into separate blocks per row.
        assert table_blocks[0]["text"].count("|") >= 8

    def test_whitespace_aligned_table_is_detected(self):
        text = (
            "Coverage overview\n"
            "Deductible          $500          $1000\n"
            "Out of pocket max   $2000         $4000\n"
            "\n"
            "This plan covers outpatient visits.\n"
        )
        blocks = extract_blocks(text)
        assert any(b["type"] == "table" for b in blocks)

    def test_single_isolated_table_like_line_is_treated_as_prose(self):
        text = "This has     several     spaced     words but is really just one line.\n"
        blocks = extract_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "prose"

    def test_preserves_order_around_a_table(self):
        text = "Intro line.\n| a | b |\n| c | d |\nOutro line.\n"
        blocks = extract_blocks(text)
        assert [b["type"] for b in blocks] == ["prose", "table", "prose"]
        assert "Intro line" in blocks[0]["text"]
        assert "Outro line" in blocks[2]["text"]


class TestSourcesFromRecords:
    def test_indexes_from_one_and_maps_fields(self):
        plan_id = str(uuid4())
        doc_id = str(uuid4())
        records = [
            {
                "plan_id": plan_id,
                "plan_name": "HealthFirst",
                "section": "Maternity",
                "document_id": doc_id,
                "chunk_index": 2,
                "page_number": 3,
                "_score": 0.87,
            }
        ]
        sources = sources_from_records(records)
        assert sources == [
            {
                "index": 1,
                "plan_id": plan_id,
                "plan_name": "HealthFirst",
                "section": "Maternity",
                "document_id": doc_id,
                "chunk_index": 2,
                "page_number": 3,
                "score": 0.87,
            }
        ]

    def test_missing_page_number_and_score_default_to_none(self):
        records = [{"plan_id": "p1", "document_id": "d1"}]
        sources = sources_from_records(records)
        assert sources[0]["page_number"] is None
        assert sources[0]["score"] is None

    def test_empty_records_yields_empty_list(self):
        assert sources_from_records([]) == []


class TestRerankPairwise:
    def test_sorts_by_independently_scored_relevance(self, monkeypatch):
        records = [
            {"text": "irrelevant", "plan_name": "A", "section": "x"},
            {"text": "highly relevant", "plan_name": "B", "section": "y"},
            {"text": "somewhat relevant", "plan_name": "C", "section": "z"},
        ]

        def fake_score(question, record):
            return {"irrelevant": 0.1, "highly relevant": 0.9, "somewhat relevant": 0.5}[
                record["text"]
            ]

        monkeypatch.setattr("backend.rag.rerank._score_one", fake_score)
        ranked = rerank_pairwise("q", records, k=2)
        assert [r["text"] for r in ranked] == ["highly relevant", "somewhat relevant"]

    def test_short_circuits_when_pool_not_larger_than_k(self, monkeypatch):
        records = [{"text": "a"}, {"text": "b"}]

        def boom(question, record):
            raise AssertionError("should not score when len(records) <= k")

        monkeypatch.setattr("backend.rag.rerank._score_one", boom)
        assert rerank_pairwise("q", records, k=2) == records

    def test_failed_scores_keep_their_fused_order_rank(self, monkeypatch):
        records = [
            {"text": "first", "id": 0},
            {"text": "second", "id": 1},
            {"text": "third", "id": 2},
        ]

        def fake_score(question, record):
            # Only the middle candidate scores; the other two fail to score.
            if record["id"] == 1:
                return 0.9
            return None

        monkeypatch.setattr("backend.rag.rerank._score_one", fake_score)
        # k < len(records) so the pool actually gets scored rather than short-circuiting.
        ranked = rerank_pairwise("q", records, k=2)
        # The scored candidate (0.9) ranks first; the unscored candidate keeps its
        # original relative position (id=0, before id=2) for the remaining slot.
        assert [r["id"] for r in ranked] == [1, 0]
