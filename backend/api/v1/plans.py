from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_security_context
from backend.core.policies import SecurityContext
from backend.schemas import PlanRead
from backend.services.plan import PlanServiceError, get_visible_plan, list_visible_plans

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=list[PlanRead])
async def list_plans(
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> list[PlanRead]:
    return await list_visible_plans(db, ctx)


@router.get("/{plan_id}", response_model=PlanRead)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> PlanRead:
    try:
        return await get_visible_plan(db, ctx, plan_id)
    except PlanServiceError as exc:
        message = str(exc)
        if message == "Plan not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message) from exc
