from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_security_context
from backend.core.policies import SecurityContext
from backend.schemas import ComparisonCreateRequest, ComparisonRequestRead
from backend.services.comparison import ComparisonServiceError, create_comparison, get_comparison

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


@router.post("", response_model=ComparisonRequestRead, status_code=status.HTTP_201_CREATED)
async def run_comparison(
    body: ComparisonCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> ComparisonRequestRead:
    try:
        return await create_comparison(db, ctx, body.plan_ids)
    except ComparisonServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{comparison_id}", response_model=ComparisonRequestRead)
async def fetch_comparison(
    comparison_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> ComparisonRequestRead:
    try:
        return await get_comparison(db, ctx, comparison_id)
    except ComparisonServiceError as exc:
        message = str(exc)
        if message == "Comparison not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message) from exc
