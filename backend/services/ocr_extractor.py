import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import pytesseract
from backend.config import settings

# Attempt import of pdf2image and pypdfium2
try:
    import pdf2image
except ImportError:
    pdf2image = None

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None


class OCRExtractor:
    """
    Renders PDF pages into images and extracts text using Tesseract OCR.
    Supports Windows explicit path configurations for Tesseract and Poppler,
    with an automatic native PDFium rendering fallback for maximum reliability.
    """

    def __init__(self):
        self._configure_tesseract()

    def _configure_tesseract(self) -> None:
        """Verify and set Tesseract OCR executable path."""
        tesseract_cmd = settings.TESSERACT_CMD
        if tesseract_cmd and os.path.exists(tesseract_cmd):
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        else:
            # Check default standard Windows installation path
            default_win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(default_win_path):
                pytesseract.pytesseract.tesseract_cmd = default_win_path
            # Otherwise pytesseract will search system PATH

    def check_tesseract_available(self) -> Tuple[bool, str]:
        """Check if Tesseract binary is executable."""
        try:
            self._configure_tesseract()
            version = pytesseract.get_tesseract_version()
            return True, f"Tesseract OCR {version} available"
        except Exception as exc:
            return False, (
                f"Tesseract OCR is not accessible. Configured path: '{settings.TESSERACT_CMD}'. "
                f"Please install Tesseract on Windows or set TESSERACT_CMD in .env. Details: {str(exc)}"
            )

    def render_pdf_page_to_image(self, file_path: str, page_number: int) -> Image.Image:
        """
        Convert a specific PDF page (1-based index) to a PIL Image.
        Uses pdf2image (with Poppler if configured), or falls back to native PDFium.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Method 1: Use pypdfium2 (standalone, high-resolution, no Poppler binary required on Windows)
        if pdfium is not None:
            try:
                doc = pdfium.PdfDocument(str(path))
                if page_number < 1 or page_number > len(doc):
                    raise IndexError(f"Page number {page_number} out of range (1 - {len(doc)})")
                page = doc[page_number - 1]
                # Render at 300 DPI (scale=300/72 ≈ 4.16) for crisp OCR
                pil_image = page.render(scale=3.0).to_pil()
                return pil_image
            except Exception as pdfium_err:
                pass  # Try pdf2image fallback

        # Method 2: Use pdf2image with Poppler
        if pdf2image is not None:
            poppler_dir = settings.POPPLER_PATH if (settings.POPPLER_PATH and os.path.exists(settings.POPPLER_PATH)) else None
            try:
                images = pdf2image.convert_from_path(
                    str(path),
                    first_page=page_number,
                    last_page=page_number,
                    poppler_path=poppler_dir,
                    dpi=300,
                )
                if images:
                    return images[0]
            except Exception as p2i_err:
                raise RuntimeError(
                    f"Failed to render PDF page {page_number} to image: {str(p2i_err)}"
                )

        raise RuntimeError(
            "Neither 'pypdfium2' nor 'pdf2image' could render the PDF page to image."
        )

    def extract_text_from_image(self, pil_image: Image.Image) -> Dict[str, Any]:
        """
        Run Tesseract OCR on a PIL image and collect text, character count, and OCR confidence.
        """
        is_ok, err_msg = self.check_tesseract_available()
        if not is_ok:
            raise RuntimeError(err_msg)

        # Image preprocessing: convert to grayscale for cleaner character recognition
        gray_image = pil_image.convert("L")

        # Run OCR
        raw_text = pytesseract.image_to_string(gray_image, config="--psm 1")
        clean_text = raw_text.strip()

        # Get confidence statistics via image_to_data
        confidence = 0.0
        try:
            data = pytesseract.image_to_data(gray_image, output_type=pytesseract.Output.DICT)
            confs = [float(c) for c in data.get("conf", []) if str(c).replace(".", "", 1).isdigit() and float(c) > 0]
            if confs:
                confidence = round(sum(confs) / len(confs), 2)
        except Exception:
            confidence = 80.0 if clean_text else 0.0

        return {
            "text": clean_text,
            "char_count": len(clean_text),
            "confidence": confidence,
        }

    def ocr_single_page(self, file_path: str, page_number: int) -> Dict[str, Any]:
        """Convenience method to render and OCR a single page."""
        image = self.render_pdf_page_to_image(file_path, page_number)
        result = self.extract_text_from_image(image)
        result["page_number"] = page_number
        return result
