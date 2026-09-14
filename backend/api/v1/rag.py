from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_security_context
from backend.core.policies import SecurityContext, can_view_provider_plans
from backend.core.rate_limit import limiter, setting_limit, user_or_ip_key
from backend.domain.enums import UserRole
from backend.rag.store import rag_configured
from backend.schemas import RagQueryRequest
from backend.services.plan import list_visible_plans
from backend.services.rag import RagServiceError, stream_rag_answer

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query")
@limiter.limit(setting_limit("rate_limit_rag_query"), key_func=user_or_ip_key)
async def rag_query(
    request: Request,
    body: RagQueryRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> StreamingResponse:
    if not rag_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG is not configured",
        )

    visible = await list_visible_plans(db, ctx)
    allowed_ids = {plan.id for plan in visible}
    if body.plan_ids:
        unknown = [plan_id for plan_id in body.plan_ids if plan_id not in allowed_ids]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="One or more plans are not visible to this user",
            )
        plan_ids = list(body.plan_ids)
    else:
        plan_ids = list(allowed_ids)

    organization_ids: list[UUID] | None = None
    if ctx.role == UserRole.HEALTHCARE_ORG_ADMIN:
        organization_ids = [ctx.organization_id]
        plan_ids = [
            plan.id
            for plan in visible
            if plan.id in set(plan_ids) and can_view_provider_plans(ctx, plan.organization_id)
        ]

    try:
        return StreamingResponse(
            stream_rag_answer(ctx, body.question, plan_ids, organization_ids),
            media_type="text/event-stream",
        )
    except RagServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
