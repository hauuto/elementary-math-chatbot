import logging
from paddleocr import PaddleOCR
from typing import Tuple

logger = logging.getLogger(__name__)

ocr = PaddleOCR(use_angle_cls=True, lang="vi")

def run_ocr(image_path_or_array) -> Tuple[str, float]:
    """
    Run PaddleOCR on an image and return (extracted text, mean confidence).
    """
    try:
        result = ocr.ocr(image_path_or_array, cls=True)
        if not result or not result[0]:
            return "", 0.0

        texts = []
        confidences = []
        for line in result[0]:
            _, (text, score) = line
            texts.append(text)
            confidences.append(score)

        full_text = " ".join(texts)
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return full_text, mean_confidence
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return "", 0.0
