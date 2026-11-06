from backend.routers.documents import router as documents_router
from backend.routers.records import router as records_router
from backend.routers.analytics import router as analytics_router
from backend.routers.export import router as export_router
from backend.routers.rag import router as rag_router

__all__ = [
    "documents_router",
    "records_router",
    "analytics_router",
    "export_router",
    "rag_router",
]
