from pathlib import Path
from typing import List, Dict, Any, Tuple
import pdfplumber
import pypdf

# Threshold: if a page has fewer characters than this, it is considered scanned or image-based
DIGITAL_TEXT_THRESHOLD_CHARS = 50


class DigitalPDFExtractor:
    """
    Extracts text from digital PDFs containing an embedded text layer using pdfplumber and pypdf.
    Preserves 1-based page numbers and character counts.
    """

    @staticmethod
    def extract_text_by_pages(file_path: str) -> List[Dict[str, Any]]:
        """
        Extract text page by page.
        Returns a list of dicts:
        [{ 'page_number': 1, 'text': '...', 'char_count': 120, 'is_digital': True }]
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document file not found at: {file_path}")

        pages_data: List[Dict[str, Any]] = []

        try:
            with pdfplumber.open(path) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ""
                    clean_text = page_text.strip()
                    char_count = len(clean_text)

                    pages_data.append({
                        "page_number": idx,
                        "text": clean_text,
                        "char_count": char_count,
                        "is_digital": char_count >= DIGITAL_TEXT_THRESHOLD_CHARS,
                    })
        except Exception as exc:
            # Fallback to pypdf if pdfplumber encounters a structural PDF parsing error
            try:
                reader = pypdf.PdfReader(str(path))
                pages_data = []
                for idx, page in enumerate(reader.pages, start=1):
                    page_text = page.extract_text() or ""
                    clean_text = page_text.strip()
                    char_count = len(clean_text)

                    pages_data.append({
                        "page_number": idx,
                        "text": clean_text,
                        "char_count": char_count,
                        "is_digital": char_count >= DIGITAL_TEXT_THRESHOLD_CHARS,
                    })
            except Exception as inner_exc:
                raise RuntimeError(
                    f"Failed to read PDF pages via both pdfplumber and pypdf: {str(exc)} | {str(inner_exc)}"
                )

        return pages_data
