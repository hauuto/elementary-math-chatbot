import logging
import numpy as np
from PIL import Image
from typing import Union
import io
import base64

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config
from pipeline.ocr import run_ocr
from pipeline.gemini_vision import get_image_info

logger = logging.getLogger(__name__)

class ImageProcessingError(Exception):
    pass

def route_image(image: Union[str, Image.Image]) -> str:
    """
    Route an image through OCR initially, and fallback to Gemini Vision if low confidence.
    If image is base64 string, decode it.
    """
    try:
        if isinstance(image, str):
            image_bytes = base64.b64decode(image)
            img = Image.open(io.BytesIO(image_bytes))
        else:
            img = image

        img = img.convert('RGB')
        img_array = np.array(img)

        ocr_text, confidence = run_ocr(img_array)
        logger.debug(f"OCR extracted (confidence={confidence:.2f}): {ocr_text[:50]}...")

        if confidence >= config.OCR_CONFIDENCE_THRESHOLD and ocr_text.strip():
            logger.debug("Routing decision: Use OCR output")
            return ocr_text.strip()
        else:
            logger.debug("Routing decision: Fallback to Gemini Vision")
            info = get_image_info(img)
            return info
    except Exception as e:
        error_msg = f"Failed to process image: {str(e)}"
        logger.error(error_msg)
        raise ImageProcessingError(error_msg)
