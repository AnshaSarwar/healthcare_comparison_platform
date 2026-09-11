from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.router import api_router
from backend.core.config import get_settings
from backend.db.seed import seed_data
from backend.db.session import async_session_factory, init_db
from backend.rag.indexing import seed_plan_documents
from backend.workers.indexing_worker import enqueue_pending_documents, run_indexing_worker

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.seed_on_startup:
        async with async_session_factory() as session:
            await seed_data(session)
            await seed_plan_documents(session)
    else:
        logger.info("SEED_ON_STARTUP=false; skipping demo seed")

    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(run_indexing_worker(stop_event))
    try:
        enqueued = await enqueue_pending_documents()
        if enqueued:
            logger.info("Enqueued %s pending documents for async indexing", enqueued)
    except Exception:
        logger.warning("Could not enqueue pending documents", exc_info=True)

    yield

    stop_event.set()
    await worker_task


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
