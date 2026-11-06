"""
Clinical Retrieval-Augmented Generation (RAG) Service for MediStruct AI.

Provides:
  - Page-aware document chunking preserving document IDs and page citations.
  - High-performance, zero-RAM-overhead lexical retrieval via SQLite FTS5 (BM25 ranking).
  - Pluggable BaseRetriever interface enabling dense semantic vector backends (e.g., ChromaDB)
    to be attached later without rewriting the retrieval or generation pipeline.
  - Strict clinical grounding via local Ollama (qwen3.5:2b) with thinking mode disabled (think: False).
  - Safety gates reusing ClinicalExtractor.get_eligible_document_text() to block unverified
    handwritten content from being indexed as confirmed evidence.
  - Transparent citation generation derived exclusively from actual database chunks.

Design Note on Retrieval Method:
  SQLiteFTS5Retriever performs lexical retrieval using the BM25 probabilistic relevance algorithm.
  It provides exact and morphological token matching for medical terms, medications, and laboratory values.
  It does not perform dense semantic similarity or vector embeddings.
"""

import abc
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text, or_

from backend.config import settings
from backend.models.clinical_records import (
    Diagnosis,
    LabResult,
    Medication,
    Recommendation,
    Symptom,
)
from backend.models.document import Document
from backend.models.patient import Patient
from backend.models.page_extraction import PageExtraction
from backend.models.schemas import RAGChunkItem, RAGSourceCitation
from backend.services.clinical_extractor import ClinicalExtractor
from backend.services.ollama_service import OllamaService


# ==============================================================================
# 1. Page-Aware Document Chunker
# ==============================================================================

class PageAwareChunker:
    """
    Splits multi-page clinical document text into manageable chunks
    while strictly preserving originating page numbers, document IDs, and filenames.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_page_text(
        self,
        document_id: str,
        filename: str,
        page_number: int,
        text: str,
        is_human_verified: bool = True,
    ) -> List[RAGChunkItem]:
        """
        Chunks text originating from a single document page.
        Chunking is isolated per page so no chunk spans across page boundaries.
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        if len(cleaned) <= self.chunk_size:
            chunk_id = f"{document_id}_p{page_number}_c0"
            return [
                RAGChunkItem(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    filename=filename,
                    page_number=page_number,
                    content=cleaned,
                    is_human_verified=is_human_verified,
                )
            ]

        # Break text on sentence or newline boundaries
        sentences = re.split(r"(?<=[.!?\n])\s+", cleaned)
        chunks: List[RAGChunkItem] = []
        current_chunk: List[str] = []
        current_len = 0
        chunk_idx = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if current_len + len(sentence) + 1 > self.chunk_size and current_chunk:
                chunk_str = " ".join(current_chunk).strip()
                chunks.append(
                    RAGChunkItem(
                        chunk_id=f"{document_id}_p{page_number}_c{chunk_idx}",
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        content=chunk_str,
                        is_human_verified=is_human_verified,
                    )
                )
                chunk_idx += 1
                # Overlap: keep the last sentence if it is small enough
                if len(current_chunk[-1]) <= self.chunk_overlap:
                    current_chunk = [current_chunk[-1], sentence]
                    current_len = len(current_chunk[0]) + len(sentence) + 1
                else:
                    current_chunk = [sentence]
                    current_len = len(sentence)
            else:
                current_chunk.append(sentence)
                current_len += len(sentence) + 1

        if current_chunk:
            chunk_str = " ".join(current_chunk).strip()
            chunks.append(
                RAGChunkItem(
                    chunk_id=f"{document_id}_p{page_number}_c{chunk_idx}",
                    document_id=document_id,
                    filename=filename,
                    page_number=page_number,
                    content=chunk_str,
                    is_human_verified=is_human_verified,
                )
            )

        return chunks


# ==============================================================================
# 2. Pluggable Retriever Interface & SQLite FTS5 Implementation
# ==============================================================================

class BaseRetriever(abc.ABC):
    """
    Abstract interface for document chunk retrieval.
    Enables swapping or augmenting SQLite FTS5 with ChromaDB / dense vectors
    without modifying the RAG query or ingestion workflow.
    """

    @abc.abstractmethod
    def index_chunks(self, db: Session, chunks: List[RAGChunkItem]) -> int:
        """Stores chunks into the retrieval index."""
        pass

    @abc.abstractmethod
    def remove_document_chunks(self, db: Session, document_id: str) -> int:
        """Removes existing chunks for a document to prevent duplicates."""
        pass

    @abc.abstractmethod
    def search(
        self,
        db: Session,
        query: str,
        top_k: int = 4,
        document_id: Optional[str] = None,
    ) -> List[Tuple[RAGChunkItem, float]]:
        """Returns list of (chunk, relevance_score) matching the query."""
        pass

    @abc.abstractmethod
    def get_index_stats(self, db: Session) -> Dict[str, Any]:
        """Returns total chunks and distinct document counts."""
        pass


class SQLiteFTS5Retriever(BaseRetriever):
    """
    Lexical retrieval backend powered by SQLite FTS5 with BM25 ranking.
    Runs entirely in-process within the existing SQLite database with 0 external packages.
    """

    def __init__(self):
        pass

    def ensure_tables(self, db: Session) -> None:
        """
        Creates rag_chunks and rag_chunks_fts virtual table if not already present.
        Safe and idempotent.
        """
        # Relational chunk metadata table
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    is_human_verified INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        # Create indexes
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_rag_doc ON rag_chunks(document_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_rag_page ON rag_chunks(document_id, page_number);"))

        # FTS5 Virtual Table
        db.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    filename UNINDEXED,
                    page_number UNINDEXED,
                    content,
                    tokenize = 'unicode61'
                );
                """
            )
        )
        db.commit()

    def remove_document_chunks(self, db: Session, document_id: str) -> int:
        """
        Removes any existing chunks for a document to prevent duplicate indexing.
        """
        self.ensure_tables(db)
        # Count existing
        res = db.execute(text("SELECT count(*) FROM rag_chunks WHERE document_id = :doc_id"), {"doc_id": document_id})
        count = res.scalar() or 0

        if count > 0:
            db.execute(text("DELETE FROM rag_chunks_fts WHERE document_id = :doc_id"), {"doc_id": document_id})
            db.execute(text("DELETE FROM rag_chunks WHERE document_id = :doc_id"), {"doc_id": document_id})
            db.commit()

        return count

    def index_chunks(self, db: Session, chunks: List[RAGChunkItem]) -> int:
        """
        Indexes a list of chunks into rag_chunks and rag_chunks_fts.
        """
        if not chunks:
            return 0

        self.ensure_tables(db)

        for c in chunks:
            # Insert into relational table
            db.execute(
                text(
                    """
                    INSERT OR REPLACE INTO rag_chunks (chunk_id, document_id, filename, page_number, content, is_human_verified)
                    VALUES (:chunk_id, :document_id, :filename, :page_number, :content, :is_human_verified);
                    """
                ),
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "filename": c.filename,
                    "page_number": c.page_number,
                    "content": c.content,
                    "is_human_verified": 1 if c.is_human_verified else 0,
                },
            )
            # Insert into FTS5 index
            db.execute(
                text(
                    """
                    INSERT INTO rag_chunks_fts (chunk_id, document_id, filename, page_number, content)
                    VALUES (:chunk_id, :document_id, :filename, :page_number, :content);
                    """
                ),
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "filename": c.filename,
                    "page_number": c.page_number,
                    "content": c.content,
                },
            )

        db.commit()
        return len(chunks)

    ENGLISH_STOP_WORDS = {
        "a", "about", "after", "all", "also", "an", "and", "any", "are", "as", "at",
        "be", "because", "been", "before", "being", "between", "both", "but", "by",
        "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for",
        "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
        "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just",
        "me", "more", "most", "my", "no", "nor", "not", "of", "off", "on", "once",
        "only", "or", "other", "our", "ours", "out", "over", "own", "s", "same", "she",
        "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
        "then", "there", "these", "they", "this", "those", "through", "to", "too",
        "under", "until", "up", "very", "was", "we", "were", "what", "when", "where",
        "which", "while", "who", "whom", "why", "will", "with", "you", "your", "yours",
    }

    def _sanitize_query_for_fts(self, raw_query: str) -> str:
        """
        Converts a user query into a safe FTS5 query string.
        Strips punctuation, filters non-informative English stop words,
        and wraps terms in quotes with OR join.
        """
        cleaned = re.sub(r'[^\w\s]', ' ', raw_query)
        raw_words = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]
        if not raw_words:
            return ""

        # Filter stop words to focus search on clinical and content keywords
        content_words = [w for w in raw_words if w.lower() not in self.ENGLISH_STOP_WORDS]
        # Fall back to raw words if all were stop words (e.g. "what is that")
        target_words = content_words if content_words else raw_words

        return " OR ".join(f'"{w}"' for w in target_words)

    def search(
        self,
        db: Session,
        query: str,
        top_k: int = 4,
        document_id: Optional[str] = None,
    ) -> List[Tuple[RAGChunkItem, float]]:
        """
        Executes a BM25 ranked FTS5 query across indexed chunks.
        """
        self.ensure_tables(db)
        fts_query = self._sanitize_query_for_fts(query)
        if not fts_query:
            return []

        try:
            sql = """
                SELECT 
                    c.chunk_id,
                    c.document_id,
                    c.filename,
                    c.page_number,
                    c.content,
                    c.is_human_verified,
                    bm25(rag_chunks_fts) as rank_score
                FROM rag_chunks_fts f
                JOIN rag_chunks c ON c.chunk_id = f.chunk_id
                WHERE rag_chunks_fts MATCH :match_query
            """
            params: Dict[str, Any] = {"match_query": fts_query, "limit": top_k}

            if document_id:
                sql += " AND c.document_id = :doc_id"
                params["doc_id"] = document_id

            sql += " ORDER BY rank_score ASC LIMIT :limit"

            rows = db.execute(text(sql), params).fetchall()

            results: List[Tuple[RAGChunkItem, float]] = []
            for r in rows:
                item = RAGChunkItem(
                    chunk_id=r[0],
                    document_id=r[1],
                    filename=r[2],
                    page_number=r[3],
                    content=r[4],
                    is_human_verified=bool(r[5]),
                )
                # BM25 in SQLite is negative (closer to zero is better). Normalize for display.
                raw_bm25 = float(r[6])
                score = round(abs(raw_bm25), 4)
                results.append((item, score))

            return results

        except Exception as exc:
            # Fallback to simple LIKE search if FTS query parsing ever encounters unexpected tokens
            return self._fallback_like_search(db, query, top_k, document_id)

    def _fallback_like_search(
        self,
        db: Session,
        query: str,
        top_k: int,
        document_id: Optional[str],
    ) -> List[Tuple[RAGChunkItem, float]]:
        """Safe fallback to LIKE substring matching if FTS expression parsing fails."""
        words = [w.strip() for w in re.sub(r'[^\w\s]', '', query).split() if len(w.strip()) > 2]
        if not words:
            return []

        sql = "SELECT chunk_id, document_id, filename, page_number, content, is_human_verified FROM rag_chunks WHERE ("
        clauses = []
        params: Dict[str, Any] = {"limit": top_k}
        for i, w in enumerate(words[:4]):
            clauses.append(f"content LIKE :w{i}")
            params[f"w{i}"] = f"%{w}%"
        sql += " OR ".join(clauses) + ")"

        if document_id:
            sql += " AND document_id = :doc_id"
            params["doc_id"] = document_id

        sql += " LIMIT :limit"

        rows = db.execute(text(sql), params).fetchall()
        results: List[Tuple[RAGChunkItem, float]] = []
        for r in rows:
            item = RAGChunkItem(
                chunk_id=r[0],
                document_id=r[1],
                filename=r[2],
                page_number=r[3],
                content=r[4],
                is_human_verified=bool(r[5]),
            )
            results.append((item, 1.0))
        return results

    def get_index_stats(self, db: Session) -> Dict[str, Any]:
        """
        Returns count of indexed chunks and documents.
        """
        self.ensure_tables(db)
        chunk_count = db.execute(text("SELECT count(*) FROM rag_chunks")).scalar() or 0
        doc_count = db.execute(text("SELECT count(DISTINCT document_id) FROM rag_chunks")).scalar() or 0
        return {
            "total_chunks": chunk_count,
            "total_documents_indexed": doc_count,
            "retrieval_backend": "sqlite_fts5_bm25",
            "backend_type": "lexical_bm25",
        }

    def clear_index(self, db: Session) -> None:
        """Resets the entire RAG chunks index."""
        self.ensure_tables(db)
        db.execute(text("DELETE FROM rag_chunks_fts"))
        db.execute(text("DELETE FROM rag_chunks"))
        db.commit()


# ==============================================================================
# 3. Clinical RAG Orchestrator Service
# ==============================================================================

class ClinicalRAGService:
    """
    Main Clinical RAG Service coordinating document safety checks, chunking,
    indexing, evidence retrieval, prompt engineering, and local Ollama inference.
    """

    INSUFFICIENT_EVIDENCE_MESSAGE = "I could not find sufficient supporting information in the uploaded documents."
    DISCLAIMER_TEXT = (
        "Academic Research & Clinical Knowledge Discovery Prototype. "
        "Answers and citations are derived from uploaded documents for research "
        "and informational purposes only and do not constitute verified medical advice."
    )

    def __init__(self, retriever: Optional[BaseRetriever] = None):
        self.chunker = PageAwareChunker(
            chunk_size=settings.RAG_CHUNK_SIZE or 500,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP or 50,
        )
        self.retriever: BaseRetriever = retriever or SQLiteFTS5Retriever()
        self.ollama = OllamaService()

    # -------------------------------------------------------------------------
    # Ingestion & Indexing Pipeline
    # -------------------------------------------------------------------------

    def index_documents(
        self,
        db: Session,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Indexes eligible uploaded documents into the retrieval store.
        Strictly applies the ClinicalExtractor safety gate:
          - Reuses ClinicalExtractor.get_eligible_document_text()
          - Blocks unverified handwritten pages from being indexed as confirmed evidence
          - Prioritizes human_corrected_text > final_text > ocr_text
          - Prevents duplicate indexing by wiping prior chunks for that document
        """
        q = db.query(Document)
        if document_id:
            q = q.filter(Document.id == document_id)

        documents = q.all()
        total_processed = len(documents)
        indexed_count = 0
        skipped_count = 0
        skipped_reasons: Dict[str, str] = {}
        total_chunks_indexed = 0

        for doc in documents:
            # 1. Apply safety gate
            is_eligible, text_content, reason = ClinicalExtractor.get_eligible_document_text(doc, db)
            if not is_eligible:
                skipped_count += 1
                skipped_reasons[doc.id] = reason or "Document ineligible for clinical evidence indexing."
                continue

            # 2. Clear old chunks for this document (prevent duplicates)
            self.retriever.remove_document_chunks(db, doc.id)

            # 3. Retrieve page extractions to assemble page-isolated chunks
            pages: List[PageExtraction] = (
                db.query(PageExtraction)
                .filter(PageExtraction.document_id == doc.id)
                .order_by(PageExtraction.page_number.asc())
                .all()
            )

            doc_chunks: List[RAGChunkItem] = []

            if pages:
                for p in pages:
                    # Select best text layer
                    best_text = p.human_corrected_text or p.final_text or p.ocr_text or ""
                    if best_text.strip():
                        chunks = self.chunker.chunk_page_text(
                            document_id=doc.id,
                            filename=doc.filename,
                            page_number=p.page_number,
                            text=best_text,
                            is_human_verified=(p.verification_status == "verified"),
                        )
                        doc_chunks.extend(chunks)
            else:
                # Fallback to document raw_text if page extraction rows are absent (e.g. digital single-page)
                if doc.raw_text and doc.raw_text.strip():
                    doc_chunks = self.chunker.chunk_page_text(
                        document_id=doc.id,
                        filename=doc.filename,
                        page_number=1,
                        text=doc.raw_text,
                        is_human_verified=True,
                    )

            if doc_chunks:
                self.retriever.index_chunks(db, doc_chunks)
                total_chunks_indexed += len(doc_chunks)
                indexed_count += 1
            else:
                skipped_count += 1
                skipped_reasons[doc.id] = "Document contained no extractable text."

        return {
            "total_documents_processed": total_processed,
            "indexed_documents_count": indexed_count,
            "skipped_documents_count": skipped_count,
            "total_chunks_indexed": total_chunks_indexed,
            "skipped_reasons": skipped_reasons,
            "retrieval_backend": "sqlite_fts5_bm25",
        }

    # -------------------------------------------------------------------------
    # Retrieval & Question Answering
    # -------------------------------------------------------------------------

    def _retrieve_structured_records(
        self,
        db: Session,
        query_text: str,
        document_id: Optional[str] = None,
        max_records: int = 8,
    ) -> List[RAGSourceCitation]:
        """
        Retrieves structured clinical database entities matching keywords in the query.
        Searches Symptoms, Diagnoses, Medications, LabResults, Recommendations, and Patient demographics.
        Strictly respects document_id filtering when provided.
        """
        lower_q = query_text.lower()
        cleaned_words = [
            w for w in re.sub(r"[^\w\s]", " ", lower_q).split()
            if len(w) > 2 and w not in SQLiteFTS5Retriever.ENGLISH_STOP_WORDS
        ]

        if not cleaned_words and not any(
            kw in lower_q for kw in ["medication", "lab", "diagnosis", "symptom", "recommendation", "patient", "prescribed", "drug"]
        ):
            return []

        doc_rows = db.query(Document.id, Document.filename).all()
        doc_filename_map = {r[0]: r[1] for r in doc_rows}

        results: List[RAGSourceCitation] = []
        seen = set()

        def add_citation(item: Any, category: str, excerpt: str, page_num: int):
            key = (category, getattr(item, "id", None))
            if key in seen:
                return
            seen.add(key)
            doc_id = getattr(item, "document_id", document_id or "")
            fname = doc_filename_map.get(doc_id, "Medical Document")
            results.append(
                RAGSourceCitation(
                    chunk_id=f"struct_{category}_{getattr(item, 'id', len(results))}",
                    document_id=doc_id,
                    filename=fname,
                    page_number=page_num or 1,
                    text_excerpt=excerpt,
                    relevance_score=1.0,
                    is_human_verified=True,
                    source_type="structured_record",
                    category=category,
                )
            )

        # 1. Medications
        med_intent = any(w in lower_q for w in ["medication", "medications", "drug", "drugs", "prescribed", "prescription", "dose", "dosage", "frequency", "route", "pill", "tablet"])
        med_q = db.query(Medication)
        if document_id:
            med_q = med_q.filter(Medication.document_id == document_id)
        if not med_intent and cleaned_words:
            clauses = [Medication.medication_name.ilike(f"%{w}%") for w in cleaned_words]
            med_q = med_q.filter(or_(*clauses))
        for m in med_q.limit(max_records).all():
            parts = [f"Medication: {m.medication_name}"]
            if m.dosage:
                parts.append(f"Dosage: {m.dosage}")
            if m.frequency:
                parts.append(f"Frequency: {m.frequency}")
            if m.route:
                parts.append(f"Route: {m.route}")
            if m.duration:
                parts.append(f"Duration: {m.duration}")
            add_citation(m, "medication", " | ".join(parts), m.page_number or 1)

        # 2. Lab Results
        lab_intent = any(w in lower_q for w in ["lab", "labs", "test", "tests", "laboratory", "result", "results", "troponin", "hemoglobin", "glucose", "ferritin", "cbc", "panel", "flag", "value", "unit"])
        lab_q = db.query(LabResult)
        if document_id:
            lab_q = lab_q.filter(LabResult.document_id == document_id)
        if not lab_intent and cleaned_words:
            clauses = [LabResult.test_name.ilike(f"%{w}%") for w in cleaned_words]
            lab_q = lab_q.filter(or_(*clauses))
        for l in lab_q.limit(max_records).all():
            parts = [f"Lab Test: {l.test_name}", f"Result: {l.result_value}"]
            if l.unit:
                parts.append(f"Unit: {l.unit}")
            if l.flag:
                parts.append(f"Flag: {l.flag}")
            if l.reference_range:
                parts.append(f"Reference Range: {l.reference_range}")
            add_citation(l, "lab_result", " | ".join(parts), l.page_number or 1)

        # 3. Diagnoses
        diag_intent = any(w in lower_q for w in ["diagnosis", "diagnoses", "condition", "disease", "disorder", "syndrome", "acute", "chronic", "confirmed", "provisional"])
        diag_q = db.query(Diagnosis)
        if document_id:
            diag_q = diag_q.filter(Diagnosis.document_id == document_id)
        if not diag_intent and cleaned_words:
            clauses = [Diagnosis.diagnosis_name.ilike(f"%{w}%") for w in cleaned_words]
            diag_q = diag_q.filter(or_(*clauses))
        for d in diag_q.limit(max_records).all():
            parts = [f"Diagnosis: {d.diagnosis_name}"]
            if d.status:
                parts.append(f"Status: {d.status}")
            if d.diagnosis_date:
                parts.append(f"Date: {d.diagnosis_date}")
            if d.description:
                parts.append(f"Details: {d.description}")
            add_citation(d, "diagnosis", " | ".join(parts), d.page_number or 1)

        # 4. Symptoms
        sym_intent = any(w in lower_q for w in ["symptom", "symptoms", "pain", "tightness", "fatigue", "fever", "cough", "dyspnea", "weakness", "complaint", "complaints"])
        sym_q = db.query(Symptom)
        if document_id:
            sym_q = sym_q.filter(Symptom.document_id == document_id)
        if not sym_intent and cleaned_words:
            clauses = [Symptom.symptom_name.ilike(f"%{w}%") for w in cleaned_words]
            sym_q = sym_q.filter(or_(*clauses))
        for s in sym_q.limit(max_records).all():
            parts = [f"Symptom: {s.symptom_name}"]
            if s.severity:
                parts.append(f"Severity: {s.severity}")
            if s.duration:
                parts.append(f"Duration: {s.duration}")
            if s.description:
                parts.append(f"Description: {s.description}")
            add_citation(s, "symptom", " | ".join(parts), s.page_number or 1)

        # 5. Recommendations
        rec_intent = any(w in lower_q for w in ["recommendation", "recommendations", "follow-up", "follow up", "plan", "instructions", "discharge", "advice", "care plan", "referral"])
        rec_q = db.query(Recommendation)
        if document_id:
            rec_q = rec_q.filter(Recommendation.document_id == document_id)
        if not rec_intent and cleaned_words:
            clauses = [Recommendation.recommendation_text.ilike(f"%{w}%") for w in cleaned_words]
            rec_q = rec_q.filter(or_(*clauses))
        for r in rec_q.limit(max_records).all():
            parts = [f"Recommendation: {r.recommendation_text}"]
            if r.follow_up_instructions:
                parts.append(f"Follow-up: {r.follow_up_instructions}")
            add_citation(r, "recommendation", " | ".join(parts), r.page_number or 1)

        # 6. Patient demographics
        pat_intent = any(w in lower_q for w in ["patient", "demographic", "demographics", "age", "gender"])
        if pat_intent:
            pat_q = db.query(Patient)
            if document_id:
                pat_q = pat_q.filter(Patient.document_id == document_id)
            for p in pat_q.limit(2).all():
                parts = ["Patient Demographics:"]
                if p.age is not None:
                    parts.append(f"Age: {p.age}")
                if p.gender:
                    parts.append(f"Gender: {p.gender}")
                if len(parts) > 1:
                    add_citation(p, "patient", " | ".join(parts), 1)

        return results[:max_records]

    def query(
        self,
        db: Session,
        query_text: str,
        document_id: Optional[str] = None,
        top_k: int = 4,
    ) -> Dict[str, Any]:
        """
        Executes dual-channel grounded clinical question-answering:
        1. Channel 1: Retrieves unstructured text chunks via SQLite FTS5 BM25.
        2. Channel 2: Retrieves verified structured clinical database records (medications, labs, diagnoses, symptoms, recommendations).
        3. Constructs source citations tagging whether evidence came from a document excerpt or structured record.
        4. If no evidence found across both channels, returns standard insufficient evidence message.
        5. Assembles dual-channel evidence into a strictly grounded prompt for local Ollama (qwen3.5:2b, think: False).
        6. Returns structured answer, multi-provenance citations, and academic research disclaimer.
        """
        cleaned_query = (query_text or "").strip()
        if not cleaned_query:
            return {
                "query": "",
                "answer": "Please provide a clinical question.",
                "sources": [],
                "sufficient_evidence": False,
                "document_filter": document_id,
                "retrieval_method": "dual_channel_fts5_and_structured_db",
                "model_used": self.ollama.model,
                "provider": "ollama",
                "disclaimer": self.DISCLAIMER_TEXT,
            }

        # Channel 1: Lexical FTS5 text search
        ranked_chunks = self.retriever.search(
            db=db,
            query=cleaned_query,
            top_k=top_k,
            document_id=document_id,
        )

        # Channel 2: Structured clinical database retrieval
        struct_citations = self._retrieve_structured_records(
            db=db,
            query_text=cleaned_query,
            document_id=document_id,
            max_records=6,
        )

        # Build text chunk citations
        text_citations: List[RAGSourceCitation] = []
        for chunk, score in ranked_chunks:
            text_citations.append(
                RAGSourceCitation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page_number=chunk.page_number,
                    text_excerpt=chunk.content[:280] + ("..." if len(chunk.content) > 280 else ""),
                    relevance_score=score,
                    is_human_verified=chunk.is_human_verified,
                    source_type="document_excerpt",
                    category=None,
                )
            )

        all_sources = struct_citations + text_citations

        # If zero evidence found across both channels, return early
        if not all_sources:
            return {
                "query": cleaned_query,
                "answer": self.INSUFFICIENT_EVIDENCE_MESSAGE,
                "sources": [],
                "sufficient_evidence": False,
                "document_filter": document_id,
                "retrieval_method": "dual_channel_fts5_and_structured_db",
                "model_used": self.ollama.model,
                "provider": "ollama",
                "disclaimer": self.DISCLAIMER_TEXT,
            }

        # Format dual-channel evidence blocks for prompt
        context_sections = []
        if struct_citations:
            sec_struct = ["--- EVIDENCE CHANNEL 1: VERIFIED STRUCTURED CLINICAL DATABASE RECORDS ---"]
            for i, sc in enumerate(struct_citations, start=1):
                cat_label = (sc.category or "record").upper()
                sec_struct.append(
                    f"[{cat_label} {i} — Source Document: {sc.filename}, Page {sc.page_number}]\n"
                    f"{sc.text_excerpt}"
                )
            context_sections.append("\n".join(sec_struct))

        if ranked_chunks:
            sec_text = ["--- EVIDENCE CHANNEL 2: VERBATIM NARRATIVE DOCUMENT EXCERPTS ---"]
            for i, (chunk, _) in enumerate(ranked_chunks, start=1):
                sec_text.append(
                    f"[EXCERPT {i} — Source Document: {chunk.filename}, Page {chunk.page_number}]\n"
                    f"{chunk.content}"
                )
            context_sections.append("\n".join(sec_text))

        context_block = "\n\n".join(context_sections)

        system_prompt = (
            "You are the clinical knowledge retrieval assistant for MediStruct AI.\n"
            "Your task is to answer the user's question STRICTLY based on the provided evidence below.\n"
            "You have access to two evidence channels:\n"
            "1. VERIFIED STRUCTURED CLINICAL RECORDS: Normalized clinical facts extracted and validated in the database (medications, lab values, diagnoses, symptoms, recommendations).\n"
            "2. VERBATIM NARRATIVE DOCUMENT EXCERPTS: Original text passages with page context.\n\n"
            "CRITICAL MEDICAL SAFETY & GROUNDING RULES:\n"
            "1. Answer ONLY using the facts stated in the provided evidence.\n"
            "2. Prioritize verified structured clinical records for exact dosages, numeric lab values, test units, and formal diagnoses. Use narrative excerpts for descriptive history and clinical context.\n"
            "3. If the provided evidence does not contain the answer, state EXACTLY:\n"
            f"   \"{self.INSUFFICIENT_EVIDENCE_MESSAGE}\"\n"
            "4. NEVER fabricate or extrapolate medical findings, prescriptions, lab values, or dates.\n"
            "5. Do NOT invent source filenames or page numbers; the software automatically cites verified sources.\n"
            "6. Maintain a factual, professional, and clinically objective tone.\n"
            "7. Keep the response concise and focused on the evidence."
        )

        user_content = (
            f"CLINICAL EVIDENCE:\n{context_block}\n\n"
            f"QUESTION: {cleaned_query}\n\n"
            "Provide a grounded clinical answer based strictly on the evidence above:"
        )

        # Call local Ollama
        try:
            payload = {
                "model": self.ollama.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.1},
            }

            resp = httpx.post(
                f"{self.ollama.base_url}/api/chat",
                json=payload,
                timeout=self.ollama.timeout,
            )
            resp.raise_for_status()
            answer_text = resp.json()["message"]["content"].strip()

        except httpx.ConnectError:
            # Server offline
            return {
                "query": cleaned_query,
                "answer": (
                    f"Local Ollama server is unreachable at {self.ollama.base_url}. "
                    "Evidence was successfully retrieved from the database, but AI synthesis requires the Ollama server to be running (ollama serve)."
                ),
                "sources": all_sources,
                "sufficient_evidence": False,
                "document_filter": document_id,
                "retrieval_method": "dual_channel_fts5_and_structured_db",
                "model_used": self.ollama.model,
                "provider": "ollama",
                "disclaimer": self.DISCLAIMER_TEXT,
            }
        except httpx.TimeoutException:
            # Inference timeout
            return {
                "query": cleaned_query,
                "answer": (
                    f"Ollama inference timed out after {self.ollama.timeout} seconds. "
                    "Evidence was retrieved from the database, but model generation took longer than expected on CPU."
                ),
                "sources": all_sources,
                "sufficient_evidence": False,
                "document_filter": document_id,
                "retrieval_method": "dual_channel_fts5_and_structured_db",
                "model_used": self.ollama.model,
                "provider": "ollama",
                "disclaimer": self.DISCLAIMER_TEXT,
            }
        except Exception as exc:
            return {
                "query": cleaned_query,
                "answer": f"Clinical RAG synthesis error: {str(exc)}",
                "sources": all_sources,
                "sufficient_evidence": False,
                "document_filter": document_id,
                "retrieval_method": "dual_channel_fts5_and_structured_db",
                "model_used": self.ollama.model,
                "provider": "ollama",
                "disclaimer": self.DISCLAIMER_TEXT,
            }

        # Check if model returned insufficient evidence statement
        sufficient = True
        lower_ans = answer_text.lower()
        if "could not find sufficient" in lower_ans or "not contain sufficient" in lower_ans or "no information" in lower_ans:
            sufficient = False

        return {
            "query": cleaned_query,
            "answer": answer_text,
            "sources": all_sources,
            "sufficient_evidence": sufficient,
            "document_filter": document_id,
            "retrieval_method": "dual_channel_fts5_and_structured_db",
            "model_used": self.ollama.model,
            "provider": "ollama",
            "disclaimer": self.DISCLAIMER_TEXT,
        }

    def get_status(self, db: Session) -> Dict[str, Any]:
        """Returns index and Ollama health status."""
        stats = self.retriever.get_index_stats(db)
        health = self.ollama.check_health()
        return {
            "total_chunks": stats["total_chunks"],
            "total_documents_indexed": stats["total_documents_indexed"],
            "retrieval_backend": stats["retrieval_backend"],
            "backend_type": stats["backend_type"],
            "ollama_model": self.ollama.model,
            "ollama_online": health.get("server_online", False),
        }
