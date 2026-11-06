from typing import Dict, Any, List
import re


class HandwritingEvaluator:
    """
    Evaluator for medical document handwriting characteristics.
    Analyzes whether documents contain handwritten doctor notes, prescriptions, or cursive annotations.
    Implements a 4-class classification pipeline:
      - 'digital': native digital PDF text layer
      - 'printed_ocr': clean scanned printed orthogonal typography
      - 'handwritten': cursive or freehand physician notes
      - 'uncertain': ambiguous or degraded scans requiring manual review
    """

    HANDWRITTEN_KEYWORDS = [
        "handwritten", "prescription", "rx", "doctor_note", "dr_note",
        "chart_note", "cursive", "scribble", "physician_order"
    ]

    @classmethod
    def classify_page(
        cls,
        filename: str,
        ocr_confidence: float,
        extracted_text: str,
        char_count: int,
        is_digital: bool = False,
        page_has_visual_content: bool = True,
    ) -> Dict[str, Any]:
        """
        4-class classification for document pages:
        'digital', 'printed_ocr', 'handwritten', or 'uncertain'.
        """
        if is_digital:
            return {
                "classification": "digital",
                "signals": ["Native digital text layer detected."],
                "recommend_gemini": False,
                "recommend_manual_review": False,
                "ocr_confidence": 100.0,
            }

        signals: List[str] = []
        weak_signals_count = 0
        fname_lower = filename.lower()

        # Strong signal: Filename keyword
        has_hw_keyword = any(keyword in fname_lower for keyword in cls.HANDWRITTEN_KEYWORDS)
        if has_hw_keyword:
            signals.append("Filename explicitly identifies handwritten or prescription document.")

        # Weak signal 1: Very low OCR confidence (< 50%) for non-empty text
        if 0 < ocr_confidence < 50.0 and char_count > 10:
            weak_signals_count += 1
            signals.append(f"Low OCR confidence ({ocr_confidence:.1f}%) suggests irregular or cursive script.")

        # Weak signal 2: High character fragmentation / noise ratio (> 40%)
        words = extracted_text.split() if extracted_text else []
        noise_ratio = 0.0
        if words and char_count > 30:
            short_broken_tokens = sum(1 for w in words if len(w) <= 2 and not w.isalnum())
            noise_ratio = short_broken_tokens / len(words)
            if noise_ratio > 0.40:
                weak_signals_count += 1
                signals.append(f"High token fragmentation ratio ({noise_ratio:.1%}) characteristic of cursive scripts.")

        # Weak signal 3: Sparse characters despite visual content
        if page_has_visual_content and 0 < char_count < 15:
            weak_signals_count += 1
            signals.append("Sparse character count despite visual page content.")

        # Moderate signal 4: Medical keywords mixed with broken tokens
        medical_stems = ["tab", "cap", "mg", "sig", "bd", "tid", "qid", "od", "po", "prn", "inj", "iv"]
        found_stems = [s for s in medical_stems if re.search(r"\b" + s + r"\b", extracted_text, re.IGNORECASE)]
        if found_stems and noise_ratio > 0.25:
            weak_signals_count += 1
            signals.append(f"Clinical abbreviations ({', '.join(found_stems)}) alongside character noise.")

        # Decision logic
        if has_hw_keyword or weak_signals_count >= 2:
            classification = "handwritten"
            recommend_gemini = True
            recommend_manual_review = False
        elif ocr_confidence >= 70.0 and noise_ratio < 0.25 and char_count > 30:
            classification = "printed_ocr"
            recommend_gemini = False
            recommend_manual_review = False
            signals.append("Clean printed OCR confidence and coherent typography.")
        elif 0 < char_count < 40 or ocr_confidence < 60.0 or noise_ratio >= 0.25:
            classification = "uncertain"
            recommend_gemini = True
            recommend_manual_review = True
            signals.append("Ambiguous scan quality: manual review and multimodal AI evaluation recommended.")
        else:
            classification = "printed_ocr"
            recommend_gemini = False
            recommend_manual_review = False

        return {
            "classification": classification,
            "signals": signals,
            "recommend_gemini": recommend_gemini,
            "recommend_manual_review": recommend_manual_review,
            "ocr_confidence": ocr_confidence,
        }

    @classmethod
    def evaluate_page(
        cls,
        filename: str,
        ocr_confidence: float,
        extracted_text: str,
        char_count: int,
    ) -> Dict[str, Any]:
        """
        Legacy evaluation method preserved for backward-compatibility with Phase 3 tests.
        """
        res = cls.classify_page(
            filename=filename,
            ocr_confidence=ocr_confidence,
            extracted_text=extracted_text,
            char_count=char_count,
            is_digital=False,
            page_has_visual_content=True,
        )

        is_handwritten = res["classification"] in ("handwritten", "uncertain")

        recommendation = (
            "Multimodal Vision AI (Gemini 3.8 Flash) recommended for clinical interpretation. "
            "Standard Tesseract OCR has documented limitations with cursive physician handwriting."
            if is_handwritten
            else "Standard OCR/Digital parsing is appropriate for printed orthogonal clinical documentation."
        )

        return {
            "handwriting_detected": is_handwritten,
            "reasons": res["signals"],
            "recommendation": recommendation,
            "ocr_confidence": ocr_confidence,
            "classification": res["classification"],
        }
