from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import get_security_context
from backend.api.v1.router import api_router
from backend.core.policies import SecurityContext, can_manage_plan_documents
from backend.domain.enums import UserRole
from backend.schemas.agent import AgentChatResponse
from backend.schemas.comparison import (
    ComparisonResultRead,
    EligibilityRuleResult,
    PlanEligibilityResult,
)
from backend.services.comparison import redact_pricing_from_comparison


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as test_client:
        yield test_client


def _parse_sse_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rag_query_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/rag/query",
        json={"question": "What is the maternity waiting period?"},
    )
    assert response.status_code == 401


def test_agents_chat_sse_shape(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    app = client.app

    async def fake_stream(
        session,
        ctx: SecurityContext,
        question: str,
        requested_plan_ids,
        thread_id: str | None = None,
    ) -> AsyncIterator[str]:
        yield 'data: {"type": "step", "node": "route", "detail": "policy_qa"}\n\n'
        yield 'data: {"type": "token", "text": "Hello "}\n\n'
        yield 'data: {"type": "token", "text": "world"}\n\n'
        payload = AgentChatResponse(
            answer="Hello world",
            citations=[],
            route="policy_qa",
            trace=[{"node": "route", "detail": "policy_qa"}],
            thread_id=thread_id or "thread-1",
        )
        yield f"data: {json.dumps({'type': 'final', **payload.model_dump(mode='json')})}\n\n"

    monkeypatch.setattr("backend.api.v1.agents.stream_agent_chat", fake_stream)

    ctx = SecurityContext(
        user_id=uuid4(),
        role=UserRole.EMPLOYER_ADMIN,
        organization_id=uuid4(),
    )
    app.dependency_overrides[get_security_context] = lambda: ctx

    response = client.post(
        "/api/v1/agents/chat",
        json={"question": "maternity waiting period", "thread_id": "thread-1"},
        headers={"Authorization": "Bearer test-token"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    types = [event["type"] for event in events]
    assert "step" in types
    assert "token" in types
    assert "final" in types
    final = next(event for event in events if event["type"] == "final")
    assert final["answer"] == "Hello world"
    assert final["thread_id"] == "thread-1"


def test_comparisons_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/comparisons", json={"plan_ids": [str(uuid4())]})
    assert response.status_code == 401


def test_employer_comparison_redacts_pricing() -> None:
    plan_id = uuid4()
    result = ComparisonResultRead(
        id=uuid4(),
        comparison_request_id=uuid4(),
        eligibility_matrix=[
            PlanEligibilityResult(
                plan_id=plan_id,
                plan_name="Test plan",
                provider_organization_id=uuid4(),
                overall_outcome="pass",
                rules=[
                    EligibilityRuleResult(
                        rule_id="budget_ceiling",
                        rule_name="Budget ceiling",
                        outcome="pass",
                        message="Estimated 100.00/employee",
                        details={"estimated_monthly_total": 15000},
                    )
                ],
                estimated_monthly_cost=15000,
                score_breakdown={"cost": 0.4},
                total_score=0.9,
            )
        ],
        scored_ranking=[plan_id],
        audit_trace={
            "plan_evaluations": [
                {
                    "score_breakdown": {"cost": 0.4},
                    "rules_evaluated": [
                        {
                            "rule_id": "budget_ceiling",
                            "message": "Estimated 100.00/employee",
                            "details": {"estimated_monthly_total": 15000},
                        }
                    ],
                }
            ]
        },
        created_at="2026-09-10T00:00:00Z",
    )

    redacted = redact_pricing_from_comparison(result)
    row = redacted.eligibility_matrix[0]
    assert row.estimated_monthly_cost is None
    assert row.score_breakdown == {}
    assert row.total_score is None
    assert row.rules[0].message == "Budget requirement evaluated"
    assert row.rules[0].details == {}
    assert redacted.audit_trace["plan_evaluations"][0]["score_breakdown"] == {}


def test_employer_can_upload_provider_policy_documents() -> None:
    employer = SecurityContext(
        user_id=uuid4(),
        role=UserRole.EMPLOYER_ADMIN,
        organization_id=uuid4(),
    )
    provider = SecurityContext(
        user_id=uuid4(),
        role=UserRole.HEALTHCARE_ORG_ADMIN,
        organization_id=uuid4(),
    )

    assert can_manage_plan_documents(employer, uuid4())
    assert not can_manage_plan_documents(provider, uuid4())
    assert can_manage_plan_documents(provider, provider.organization_id)
