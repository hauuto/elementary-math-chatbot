import os
import io
import logging
from google import genai
from PIL import Image

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

logger = logging.getLogger(__name__)

client = genai.Client(api_key=config.GEMINI_API_KEY)

def get_image_info(image: Image.Image) -> str:
    """
    Call Gemini Vision API to classify image type and extract information.
    Classification prompt:
    "Ảnh này là hình học/hình khối, hay ảnh bài toán có chữ khó đọc,
    hay ảnh minh họa bài toán? Hãy trả lời bằng một trong ba loại:
    'hình học', 'chữ', 'minh họa'."
    """
    try:
        classifier_prompt = (
            "Ảnh này là hình học/hình khối, hay ảnh bài toán có chữ khó đọc, "
            "hay ảnh minh họa bài toán? Hãy trả lời bằng một trong ba loại: "
            "'hình học', 'chữ', 'minh họa'."
        )

        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[image, classifier_prompt]
        )
        image_type = response.text.strip().lower()

        if "hình học" in image_type:
            task_prompt = "Hãy mô tả chi tiết các hình học, kích thước, và các thông tin liên quan trong ảnh bằng tiếng Việt."
        elif "chữ" in image_type:
            task_prompt = "Hãy trích xuất toàn bộ văn bản trong ảnh cẩn thận và chính xác bằng tiếng Việt."
        else:
            task_prompt = "Hãy mô tả ngắn gọn bối cảnh hoặc các chi tiết quan trọng liên quan đến bài toán trong ảnh bằng tiếng Việt."

        final_response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[image, task_prompt]
        )
        return final_response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API failed: {e}")
        raise
