from backend.services.pdf_extractor import DigitalPDFExtractor
from backend.services.ocr_extractor import OCRExtractor
from backend.services.handwriting_evaluator import HandwritingEvaluator
from backend.services.document_processor import DocumentProcessor

__all__ = [
    "DigitalPDFExtractor",
    "OCRExtractor",
    "HandwritingEvaluator",
    "DocumentProcessor",
]
