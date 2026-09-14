from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_security_context
from backend.core.policies import SecurityContext
from backend.core.rate_limit import limiter, setting_limit, user_or_ip_key
from backend.schemas.agent import AgentChatRequest
from backend.services.agent import AgentServiceError, stream_agent_chat

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/chat")
@limiter.limit(setting_limit("rate_limit_agents_chat"), key_func=user_or_ip_key)
async def agent_chat(
    request: Request,
    body: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> StreamingResponse:
    try:
        return StreamingResponse(
            stream_agent_chat(db, ctx, body.question, body.plan_ids, body.thread_id),
            media_type="text/event-stream",
        )
    except AgentServiceError as exc:
        message = str(exc)
        code = status.HTTP_503_SERVICE_UNAVAILABLE
        if "not visible" in message.lower():
            code = status.HTTP_403_FORBIDDEN
        elif "no visible plans" in message.lower():
            code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=message) from exc
