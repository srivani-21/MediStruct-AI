from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schemas import (
    RAGChunkItem,
    RAGIndexRequest,
    RAGIndexResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGStatusResponse,
)
from backend.services.rag_service import ClinicalRAGService

router = APIRouter(prefix="/api/rag", tags=["Clinical RAG"])


def get_rag_service() -> ClinicalRAGService:
    return ClinicalRAGService()


@router.get("/status", response_model=RAGStatusResponse)
def get_rag_status(
    db: Session = Depends(get_db),
    rag_svc: ClinicalRAGService = Depends(get_rag_service),
):
    """
    Returns retrieval index status and local Ollama inference server connectivity.
    """
    try:
        return rag_svc.get_status(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch RAG status: {str(exc)}")


@router.post("/index", response_model=RAGIndexResponse)
def index_documents(
    payload: RAGIndexRequest = RAGIndexRequest(),
    db: Session = Depends(get_db),
    rag_svc: ClinicalRAGService = Depends(get_rag_service),
):
    """
    Indexes eligible medical documents into the SQLite FTS5 BM25 retrieval index.
    Strictly applies the ClinicalExtractor safety gate:
      - Human verification is required for handwritten notes before indexing.
      - Human-corrected text is prioritized over OCR text.
      - Chunks are page-isolated to guarantee citation accuracy.
    """
    try:
        return rag_svc.index_documents(db, document_id=payload.document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to index documents: {str(exc)}")


@router.post("/query", response_model=RAGQueryResponse)
def query_clinical_rag(
    payload: RAGQueryRequest,
    db: Session = Depends(get_db),
    rag_svc: ClinicalRAGService = Depends(get_rag_service),
):
    """
    Performs evidence-grounded clinical question-answering:
    1. Retrieves top-K database chunks matching the query.
    2. Builds citations strictly from retrieved database chunks.
    3. Assembles grounded context and queries local Ollama (qwen3.5:2b).
    4. Enforces no-hallucination and standard research disclaimers.
    """
    try:
        return rag_svc.query(
            db=db,
            query_text=payload.query,
            document_id=payload.document_id,
            top_k=payload.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clinical RAG query failed: {str(exc)}")


@router.get("/chunks", response_model=List[RAGChunkItem])
def list_indexed_chunks(
    document_id: Optional[str] = Query(None, description="Optional document ID filter"),
    db: Session = Depends(get_db),
    rag_svc: ClinicalRAGService = Depends(get_rag_service),
):
    """
    Lists indexed chunks for audit, citation verification, and debugging.
    """
    try:
        rag_svc.retriever.ensure_tables(db)
        sql = "SELECT chunk_id, document_id, filename, page_number, content, is_human_verified FROM rag_chunks"
        params: Dict[str, Any] = {}
        if document_id:
            sql += " WHERE document_id = :doc_id"
            params["doc_id"] = document_id
        sql += " ORDER BY document_id, page_number, chunk_id"

        rows = db.execute(text(sql), params).fetchall()
        return [
            RAGChunkItem(
                chunk_id=r[0],
                document_id=r[1],
                filename=r[2],
                page_number=r[3],
                content=r[4],
                is_human_verified=bool(r[5]),
            )
            for r in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chunks: {str(exc)}")


@router.delete("/index")
def clear_rag_index(
    db: Session = Depends(get_db),
    rag_svc: ClinicalRAGService = Depends(get_rag_service),
):
    """
    Resets the SQLite FTS5 RAG index.
    """
    try:
        rag_svc.retriever.clear_index(db)
        return {"status": "success", "message": "RAG retrieval index cleared successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear RAG index: {str(exc)}")
