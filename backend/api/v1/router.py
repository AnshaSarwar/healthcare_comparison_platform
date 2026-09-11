from fastapi import APIRouter

from backend.api.v1 import admin, agents, auth, comparisons, documents, plans, rag

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(plans.router)
api_router.include_router(comparisons.router)
api_router.include_router(documents.router)
api_router.include_router(rag.router)
api_router.include_router(agents.router)
