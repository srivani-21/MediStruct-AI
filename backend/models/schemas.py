from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# Patient Schemas
# ==============================================================================

class PatientBase(BaseModel):
    patient_identifier: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    demographic_notes: Optional[str] = None


class PatientCreate(PatientBase):
    document_id: Optional[str] = None


class PatientResponse(PatientBase):
    id: int
    document_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Symptom Schemas
# ==============================================================================

class SymptomBase(BaseModel):
    symptom_name: str
    description: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[str] = None
    page_number: Optional[int] = None


class SymptomCreate(SymptomBase):
    document_id: str
    patient_id: Optional[int] = None


class SymptomResponse(SymptomBase):
    id: int
    document_id: str
    patient_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Diagnosis Schemas
# ==============================================================================

class DiagnosisBase(BaseModel):
    diagnosis_name: str
    description: Optional[str] = None
    diagnosis_date: Optional[str] = None
    status: Optional[str] = None
    page_number: Optional[int] = None


class DiagnosisCreate(DiagnosisBase):
    document_id: str
    patient_id: Optional[int] = None


class DiagnosisResponse(DiagnosisBase):
    id: int
    document_id: str
    patient_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Medication Schemas
# ==============================================================================

class MedicationBase(BaseModel):
    medication_name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    route: Optional[str] = None
    page_number: Optional[int] = None


class MedicationCreate(MedicationBase):
    document_id: str
    patient_id: Optional[int] = None


class MedicationResponse(MedicationBase):
    id: int
    document_id: str
    patient_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Lab Result Schemas
# ==============================================================================

class LabResultBase(BaseModel):
    test_name: str
    result_value: str
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: Optional[str] = None
    test_date: Optional[str] = None
    page_number: Optional[int] = None


class LabResultCreate(LabResultBase):
    document_id: str
    patient_id: Optional[int] = None


class LabResultResponse(LabResultBase):
    id: int
    document_id: str
    patient_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Recommendation Schemas
# ==============================================================================

class RecommendationBase(BaseModel):
    recommendation_text: str
    follow_up_instructions: Optional[str] = None
    page_number: Optional[int] = None


class RecommendationCreate(RecommendationBase):
    document_id: str
    patient_id: Optional[int] = None


class RecommendationResponse(RecommendationBase):
    id: int
    document_id: str
    patient_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Document Schemas
# ==============================================================================

class DocumentBase(BaseModel):
    filename: str
    file_size_bytes: int = 0
    page_count: int = 0
    document_type: str = "unknown"
    handwriting_detected: bool = False
    extraction_method: str = "pending"
    processing_status: str = "PENDING"


class DocumentResponse(DocumentBase):
    id: str
    character_count: int = 0
    error_message: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentResponse):
    raw_text: Optional[str] = None
    patient: Optional[PatientResponse] = None
    record_counts: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Batch Clinical Structuring Input Schema
# ==============================================================================

class StructuredClinicalPayload(BaseModel):
    """Payload representing fully structured clinical extraction results from Gemini."""
    document_id: str
    patient: Optional[PatientBase] = None
    symptoms: List[SymptomBase] = Field(default_factory=list)
    diagnoses: List[DiagnosisBase] = Field(default_factory=list)
    medications: List[MedicationBase] = Field(default_factory=list)
    lab_results: List[LabResultBase] = Field(default_factory=list)
    recommendations: List[RecommendationBase] = Field(default_factory=list)


# ==============================================================================
# Overview Metrics Schema
# ==============================================================================

class OverviewMetricsResponse(BaseModel):
    total_documents: int = 0
    successfully_processed_documents: int = 0
    total_patients: int = 0
    total_symptoms: int = 0
    total_diagnoses: int = 0
    total_medications: int = 0
    total_lab_tests: int = 0
    total_recommendations: int = 0

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Page Extraction & Verification Schemas
# ==============================================================================

class PageExtractionResponse(BaseModel):
    id: str
    document_id: str
    page_number: int
    page_classification: str
    extraction_method: str
    ocr_text: Optional[str] = None
    ocr_confidence: Optional[float] = None
    gemini_text: Optional[str] = None
    final_text: Optional[str] = None
    human_corrected_text: Optional[str] = None
    verification_status: str
    unclear_count: int = 0
    has_unclear_markers: bool = False
    image_available: bool = False
    gemini_fallback_used: bool = False
    gemini_error: Optional[str] = None
    human_verified_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerifyRequest(BaseModel):
    human_corrected_text: str


# ==============================================================================
# Phase 5: Clinical Knowledge Discovery & Analytics Schemas
# ==============================================================================

class CategoryDistributionItem(BaseModel):
    category: str
    count: int
    percentage: float


class ClinicalSummaryResponse(BaseModel):
    total_documents: int
    total_patients: int
    total_symptoms: int
    total_diagnoses: int
    total_medications: int
    total_lab_results: int
    total_recommendations: int
    total_clinical_entities: int
    category_distribution: List[CategoryDistributionItem]


class SymptomFrequencyItem(BaseModel):
    symptom_name: str
    count: int
    document_count: int
    severity_breakdown: Dict[str, int] = {}
    supporting_pages: List[int] = []
    supporting_documents: List[str] = []


class DiagnosisFrequencyItem(BaseModel):
    diagnosis_name: str
    count: int
    document_count: int
    status_breakdown: Dict[str, int] = {}
    supporting_pages: List[int] = []
    supporting_documents: List[str] = []


class MedicationFrequencyItem(BaseModel):
    medication_name: str
    count: int
    document_count: int
    route_breakdown: Dict[str, int] = {}
    sample_dosages: List[str] = []
    supporting_pages: List[int] = []
    supporting_documents: List[str] = []


class CoOccurrenceItem(BaseModel):
    symptom_name: Optional[str] = None
    medication_name: Optional[str] = None
    diagnosis_name: str
    co_occurrence_count: int
    supporting_documents: List[str] = []
    supporting_pages: List[int] = []
    statistical_association_only: bool = True
    clinical_causation_claimed: bool = False


class LabAnalyticsItem(BaseModel):
    test_name: str
    unit: str
    total_records: int
    document_count: int
    numeric_record_count: int
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    avg_value: Optional[float] = None
    flag_breakdown: Dict[str, int] = {}
    documented_reference_ranges: List[str] = []
    sample_values: List[str] = []
    supporting_pages: List[int] = []
    supporting_documents: List[str] = []


class RecommendationAnalyticsRecord(BaseModel):
    id: int
    recommendation_text: str
    follow_up_instructions: Optional[str] = None
    page_number: Optional[int] = None
    document_id: str


class RecommendationAnalyticsResponse(BaseModel):
    total_recommendations: int
    with_follow_up_instructions_count: int
    without_follow_up_count: int
    recommendation_records: List[RecommendationAnalyticsRecord]


class DescriptiveInsightItem(BaseModel):
    title: str
    category: str
    observation: str
    supporting_count: int
    document_count: int


# ==============================================================================
# Phase 6: Dataset Export Schemas
# ==============================================================================

class ExportSummaryResponse(BaseModel):
    document_filter: Optional[str] = None
    total_documents: int
    categories: Dict[str, int]
    total_records: int
    de_identification_default: bool = True
    export_formats: List[str] = ["excel", "csv", "bundle", "json"]


# ==============================================================================
# Phase 7: Clinical RAG Schemas
# ==============================================================================

class RAGChunkItem(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    content: str
    is_human_verified: bool = True


class RAGSourceCitation(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    text_excerpt: str
    relevance_score: Optional[float] = None
    is_human_verified: bool = True
    source_type: str = "document_excerpt"  # "document_excerpt" or "structured_record"
    category: Optional[str] = None         # "symptom" | "diagnosis" | "medication" | "lab_result" | "recommendation" | "patient"


class RAGQueryRequest(BaseModel):
    query: str
    document_id: Optional[str] = None
    top_k: int = Field(default=4, ge=1, le=10)


class RAGQueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[RAGSourceCitation] = []
    sufficient_evidence: bool = True
    document_filter: Optional[str] = None
    retrieval_method: str = "dual_channel_fts5_and_structured_db"
    model_used: str = "qwen3.5:2b"
    provider: str = "ollama"
    disclaimer: str = (
        "Academic Research & Clinical Knowledge Discovery Prototype. "
        "Answers and citations are derived from uploaded documents for research "
        "and informational purposes only and do not constitute verified medical advice."
    )


class RAGIndexRequest(BaseModel):
    document_id: Optional[str] = None


class RAGIndexResponse(BaseModel):
    total_documents_processed: int
    indexed_documents_count: int
    skipped_documents_count: int
    total_chunks_indexed: int
    skipped_reasons: Dict[str, str] = {}
    retrieval_backend: str = "sqlite_fts5_bm25"


class RAGStatusResponse(BaseModel):
    total_chunks: int
    total_documents_indexed: int
    retrieval_backend: str = "sqlite_fts5_bm25"
    backend_type: str = "lexical_bm25"
    ollama_model: str
    ollama_online: bool




