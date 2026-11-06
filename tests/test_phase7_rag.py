import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import httpx

from backend.database import Base, get_db
from backend.main import app
from backend.models.document import Document
from backend.models.page_extraction import PageExtraction
from backend.models.clinical_records import (
    Diagnosis,
    LabResult,
    Medication,
    Recommendation,
    Symptom,
)
from backend.services.rag_service import (
    PageAwareChunker,
    SQLiteFTS5Retriever,
    ClinicalRAGService,
)


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def test_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        # Clean RAG tables if present from prior runs on shared connection
        try:
            db.execute(text("DROP TABLE IF EXISTS rag_chunks_fts;"))
            db.execute(text("DROP TABLE IF EXISTS rag_chunks;"))
            db.commit()
        except Exception:
            pass

        # Seed test documents
        doc1 = Document(
            id="doc-cardio-101",
            filename="Cardiology_Discharge.pdf",
            stored_path="/mock/path/doc1.pdf",
            file_size_bytes=15000,
            page_count=2,
            document_type="digital",
            extraction_method="pdfplumber",
            character_count=2000,
            processing_status="COMPLETED",
        )
        doc2 = Document(
            id="doc-handwritten-202",
            filename="Physician_Handwritten_Notes.pdf",
            stored_path="/mock/path/doc2.pdf",
            file_size_bytes=25000,
            page_count=1,
            document_type="handwritten",
            extraction_method="gemini_vision",
            character_count=600,
            processing_status="COMPLETED",
            handwriting_detected=True,
        )
        doc3 = Document(
            id="doc-lab-303",
            filename="Hematology_Report.pdf",
            stored_path="/mock/path/doc3.pdf",
            file_size_bytes=12000,
            page_count=1,
            document_type="digital",
            extraction_method="pdfplumber",
            character_count=900,
            processing_status="COMPLETED",
        )
        db.add_all([doc1, doc2, doc3])
        db.commit()

        # Seed page extractions
        # Doc 1: Page 1 (History) and Page 2 (Medications & Follow-up)
        p1 = PageExtraction(
            id="pe-cardio-p1",
            document_id="doc-cardio-101",
            page_number=1,
            page_classification="digital",
            extraction_method="pdfplumber",
            final_text="Patient presents with substernal chest pain radiating to left arm. Diagnosis: Acute Coronary Syndrome. Troponin I elevated at 0.08 ng/mL.",
            verification_status="verified",
        )
        p2 = PageExtraction(
            id="pe-cardio-p2",
            document_id="doc-cardio-101",
            page_number=2,
            page_classification="digital",
            extraction_method="pdfplumber",
            ocr_text="Prescribed Aspirin 81mg orally daily and Atorvastatin 40mg at bedtime.",
            human_corrected_text="Prescribed Aspirin 81mg orally daily, Clopidogrel 75mg daily, and Atorvastatin 40mg at bedtime. Follow up with Cardiology in 2 weeks.",
            final_text="Prescribed Aspirin 81mg orally daily and Atorvastatin 40mg at bedtime.",
            verification_status="verified",
        )

        # Doc 2: Unverified handwritten notes
        p3 = PageExtraction(
            id="pe-hw-p1",
            document_id="doc-handwritten-202",
            page_number=1,
            page_classification="handwritten",
            extraction_method="gemini_vision",
            ocr_text="Uncertain scribbles regarding abdominal palpation and tenderness.",
            final_text="Uncertain scribbles regarding abdominal palpation and tenderness.",
            verification_status="pending",  # Unverified!
        )

        # Doc 3: Lab report
        p4 = PageExtraction(
            id="pe-lab-p1",
            document_id="doc-lab-303",
            page_number=1,
            page_classification="digital",
            extraction_method="pdfplumber",
            final_text="Complete Blood Count: Hemoglobin 9.4 g/dL (Low), Ferritin 12 ng/mL (Low). Prescribed Ferrous Sulfate 325mg twice daily.",
            verification_status="verified",
        )

        db.add_all([p1, p2, p3, p4])
        db.commit()

        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# Unit Tests: PageAwareChunker
# ==============================================================================

def test_page_preserving_chunker():
    chunker = PageAwareChunker(chunk_size=100, chunk_overlap=20)
    text = (
        "Patient presented with chest tightness and severe dyspnea on minimal exertion. "
        "Electrocardiogram revealed ST-segment elevation in anterior leads V1-V4. "
        "Emergent coronary angiography was performed."
    )
    chunks = chunker.chunk_page_text(
        document_id="doc-test-1",
        filename="Test_Report.pdf",
        page_number=3,
        text=text,
        is_human_verified=True,
    )
    assert len(chunks) >= 2
    for c in chunks:
        assert c.document_id == "doc-test-1"
        assert c.filename == "Test_Report.pdf"
        assert c.page_number == 3
        assert c.is_human_verified is True
        assert c.chunk_id.startswith("doc-test-1_p3_")


# ==============================================================================
# Unit & Integration Tests: Ingestion, Safety Gate & FTS5 Retrieval
# ==============================================================================

def test_human_verification_safety_gate_blocks_unverified(test_db):
    rag_svc = ClinicalRAGService()
    res = rag_svc.index_documents(test_db)

    # 3 total documents
    assert res["total_documents_processed"] == 3
    # doc-cardio-101 and doc-lab-303 should be indexed
    assert res["indexed_documents_count"] == 2
    # doc-handwritten-202 must be skipped due to unverified handwriting!
    assert res["skipped_documents_count"] == 1
    assert "doc-handwritten-202" in res["skipped_reasons"]
    assert "unverified handwritten" in res["skipped_reasons"]["doc-handwritten-202"].lower()


def test_human_corrected_text_priority(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db, document_id="doc-cardio-101")

    # In p2, human_corrected_text has "Clopidogrel 75mg daily", while raw ocr_text does NOT
    hits = rag_svc.retriever.search(test_db, query="Clopidogrel", top_k=4)
    assert len(hits) >= 1
    chunk, score = hits[0]
    assert chunk.document_id == "doc-cardio-101"
    assert chunk.page_number == 2
    assert "Clopidogrel 75mg" in chunk.content


def test_sqlite_fts5_bm25_retrieval(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    # Search for troponin
    results = rag_svc.retriever.search(test_db, query="Troponin", top_k=2)
    assert len(results) >= 1
    top_chunk, score = results[0]
    assert "Troponin I" in top_chunk.content
    assert top_chunk.document_id == "doc-cardio-101"
    assert top_chunk.page_number == 1
    assert score is not None


def test_document_scope_filtering(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    # Query for "Prescribed" scoped to doc-lab-303
    hits = rag_svc.retriever.search(test_db, query="Prescribed", top_k=5, document_id="doc-lab-303")
    assert len(hits) >= 1
    for chunk, _ in hits:
        assert chunk.document_id == "doc-lab-303"
        assert "Ferrous Sulfate" in chunk.content
        assert "Aspirin" not in chunk.content  # Aspirin is in doc-cardio-101


def test_top_k_behavior(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    hits_k1 = rag_svc.retriever.search(test_db, query="Prescribed", top_k=1)
    assert len(hits_k1) == 1

    hits_k2 = rag_svc.retriever.search(test_db, query="Prescribed", top_k=2)
    assert len(hits_k2) == 2


def test_duplicate_indexing_prevention(test_db):
    rag_svc = ClinicalRAGService()
    # Reset index for clean state
    rag_svc.retriever.clear_index(test_db)

    # Index once
    rag_svc.index_documents(test_db, document_id="doc-cardio-101")
    stats1 = rag_svc.retriever.get_index_stats(test_db)
    assert stats1["total_documents_indexed"] == 1

    # Index again for the exact same document
    rag_svc.index_documents(test_db, document_id="doc-cardio-101")
    stats2 = rag_svc.retriever.get_index_stats(test_db)

    # Total chunks must NOT double
    assert stats1["total_chunks"] == stats2["total_chunks"]
    assert stats2["total_documents_indexed"] == 1


# ==============================================================================
# Unit & Integration Tests: Grounded Answer Generation & Citation Correctness
# ==============================================================================

def test_citation_correctness_from_real_database_chunks(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "The patient was prescribed Aspirin 81mg and Atorvastatin."}
    }

    with patch("httpx.post", return_value=mock_resp):
        res = rag_svc.query(test_db, query_text="What medications were prescribed for the heart condition?", top_k=2)

    assert res["sufficient_evidence"] is True
    assert len(res["sources"]) >= 1
    citation = res["sources"][0]
    # Check citation is directly from database
    assert citation.document_id == "doc-cardio-101"
    assert citation.filename == "Cardiology_Discharge.pdf"
    assert citation.page_number in (1, 2)
    assert citation.text_excerpt != ""


def test_grounded_answer_generation_with_ollama(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "Based on the records, the patient has an elevated Troponin I level of 0.08 ng/mL."}
    }

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        res = rag_svc.query(test_db, query_text="What was the troponin level?")

        # Verify payload sent to Ollama
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["think"] is False
        assert payload["options"]["temperature"] == 0.1
        assert "Troponin" in payload["messages"][1]["content"]

    assert "0.08 ng/mL" in res["answer"]
    assert res["disclaimer"] != ""


def test_insufficient_evidence_when_no_chunks_found(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    # Search for an entity not in any document
    res = rag_svc.query(test_db, query_text="astronaut spacecraft lunar orbit mars rover")
    assert res["sufficient_evidence"] is False
    assert res["answer"] == "I could not find sufficient supporting information in the uploaded documents."
    assert res["sources"] == []


def test_insufficient_evidence_model_refusal_with_sources(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    # Mock Ollama returning standard insufficient evidence when chunks are found
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "I could not find sufficient supporting information in the uploaded documents."}
    }

    with patch("httpx.post", return_value=mock_resp):
        res = rag_svc.query(test_db, query_text="What is the patient's favorite hobby?")

    assert res["sufficient_evidence"] is False
    assert "could not find sufficient" in res["answer"].lower()


def test_ollama_offline_handling(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    with patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")):
        res = rag_svc.query(test_db, query_text="What is the diagnosis?")

    assert res["sufficient_evidence"] is False
    assert "Ollama server is unreachable" in res["answer"]
    # Evidence was still retrieved from the database!
    assert len(res["sources"]) >= 1


def test_ollama_timeout_handling(test_db):
    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    with patch("httpx.post", side_effect=httpx.TimeoutException("Read timed out")):
        res = rag_svc.query(test_db, query_text="What is the diagnosis?")

    assert res["sufficient_evidence"] is False
    assert "timed out" in res["answer"]


# ==============================================================================
# API Endpoint Integration Tests
# ==============================================================================

def test_api_rag_status_and_index_flow(client):
    # 1. Check status before indexing
    status_res = client.get("/api/rag/status")
    assert status_res.status_code == 200
    assert "retrieval_backend" in status_res.json()

    # 2. Trigger index
    idx_res = client.post("/api/rag/index", json={})
    assert idx_res.status_code == 200
    idx_data = idx_res.json()
    assert idx_data["indexed_documents_count"] == 2
    assert idx_data["skipped_documents_count"] == 1

    # 3. List chunks
    chunks_res = client.get("/api/rag/chunks")
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()
    assert len(chunks) >= 3

    # 4. Clear index
    del_res = client.delete("/api/rag/index")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify chunks are 0
    chunks_after = client.get("/api/rag/chunks").json()
    assert len(chunks_after) == 0


def test_api_rag_query_endpoint(client):
    # Index first
    client.post("/api/rag/index", json={})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "Hemoglobin was 9.4 g/dL and Ferritin was 12 ng/mL."}
    }

    with patch("httpx.post", return_value=mock_resp):
        res = client.post(
            "/api/rag/query",
            json={"query": "What were the hemoglobin lab results?", "top_k": 3},
        )
        assert res.status_code == 200
        body = res.json()
        assert "9.4 g/dL" in body["answer"]
        assert len(body["sources"]) >= 1
        assert body["retrieval_method"] == "dual_channel_fts5_and_structured_db"


# ==============================================================================
# Dual-Channel Retrieval Integration Tests
# ==============================================================================

def test_dual_channel_structured_medication_retrieval(test_db):
    # Seed structured medications
    med = Medication(
        id=1,
        document_id="doc-cardio-101",
        medication_name="Aspirin",
        dosage="81mg",
        frequency="Once daily",
        route="Oral",
        duration="Indefinite",
        page_number=2,
    )
    test_db.add(med)
    test_db.commit()

    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "The patient was prescribed Aspirin 81mg orally daily."}
    }

    with patch("httpx.post", return_value=mock_resp):
        res = rag_svc.query(test_db, query_text="What medications were prescribed?", top_k=2)

    assert res["sufficient_evidence"] is True
    # Find structured citation
    struct_sources = [s for s in res["sources"] if s.source_type == "structured_record"]
    assert len(struct_sources) >= 1
    med_src = struct_sources[0]
    assert med_src.category == "medication"
    assert "Aspirin" in med_src.text_excerpt
    assert "81mg" in med_src.text_excerpt
    assert med_src.document_id == "doc-cardio-101"
    assert med_src.page_number == 2


def test_dual_channel_structured_lab_value_precision(test_db):
    # Seed structured lab result
    lab = LabResult(
        id=1,
        document_id="doc-cardio-101",
        test_name="Troponin I",
        result_value="0.08",
        numeric_value=0.08,
        unit="ng/mL",
        reference_range="< 0.04",
        flag="High",
        page_number=1,
    )
    test_db.add(lab)
    test_db.commit()

    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "Troponin I was elevated at 0.08 ng/mL with reference range < 0.04."}
    }

    with patch("httpx.post", return_value=mock_resp):
        res = rag_svc.query(test_db, query_text="What was the troponin lab test result?", top_k=2)

    assert res["sufficient_evidence"] is True
    struct_sources = [s for s in res["sources"] if s.source_type == "structured_record" and s.category == "lab_result"]
    assert len(struct_sources) >= 1
    lab_src = struct_sources[0]
    assert "Troponin I" in lab_src.text_excerpt
    assert "0.08" in lab_src.text_excerpt
    assert "ng/mL" in lab_src.text_excerpt
    assert "High" in lab_src.text_excerpt


def test_dual_channel_document_scope_isolation(test_db):
    # Seed medications in both doc-cardio-101 and doc-lab-303
    m1 = Medication(
        id=10,
        document_id="doc-cardio-101",
        medication_name="Atorvastatin",
        dosage="40mg",
        page_number=2,
    )
    m2 = Medication(
        id=20,
        document_id="doc-lab-303",
        medication_name="Ferrous Sulfate",
        dosage="325mg",
        page_number=1,
    )
    test_db.add_all([m1, m2])
    test_db.commit()

    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    # Query scoped to doc-lab-303 only
    struct_sources = rag_svc._retrieve_structured_records(
        db=test_db,
        query_text="medications",
        document_id="doc-lab-303",
    )
    assert len(struct_sources) >= 1
    for s in struct_sources:
        assert s.document_id == "doc-lab-303"
        assert "Ferrous Sulfate" in s.text_excerpt
        assert "Atorvastatin" not in s.text_excerpt


def test_dual_channel_both_evidence_channels_present(test_db):
    # Seed structured diagnosis
    diag = Diagnosis(
        id=5,
        document_id="doc-cardio-101",
        diagnosis_name="Acute Coronary Syndrome",
        status="Confirmed",
        page_number=1,
    )
    test_db.add(diag)
    test_db.commit()

    rag_svc = ClinicalRAGService()
    rag_svc.index_documents(test_db)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "Acute Coronary Syndrome confirmed."}
    }

    with patch("httpx.post", return_value=mock_resp):
        res = rag_svc.query(test_db, query_text="What is the diagnosis?", top_k=2)

    sources = res["sources"]
    types = {s.source_type for s in sources}
    # Both document_excerpt and structured_record are present
    assert "structured_record" in types
    assert "document_excerpt" in types

