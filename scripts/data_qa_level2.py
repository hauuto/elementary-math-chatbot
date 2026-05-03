import os
import logging
import pandas as pd
import re
import ast
import time
import sys
import requests
import json

# Add config import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from config import LM_STUDIO_URL, GEMINI_API_KEY
except ImportError:
    LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
    GEMINI_API_KEY = ""

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def extract_answer(text: str) -> str:
    """
    Trích xuất kết quả từ CoT một cách thông minh hơn.
    """
    text = str(text).lower()

    # 1. Tìm các từ khoá kết luận rõ ràng (đáp số: X, chọn: A, đáp án là D)
    match = re.search(r'(?:đáp số|kết quả|với|chọn|đáp án|khoanh vào|là)(?:\s*đáp án)?[:\s]+([a-d]|[-0-9.,/]+)', text)
    if match:
        val = match.group(1).rstrip('., ')
        if val in ['a', 'b', 'c', 'd']:
            return val
        return val.replace(',', '.')

    # 2. Rút trích số hoặc chữ cái đáp án cuối cùng nếu không có từ khoá
    # Tìm kiếm một chữ cái A,B,C,D đứng trước dấu chấm ở cuối câu (ví dụ "... Vậy chọn D.")
    final_choice = re.search(r'\b([a-d])\s*\.$', text)
    if final_choice:
        return final_choice.group(1)

    numbers = re.findall(r'[-0-9.,/]+', text)
    if numbers:
        return numbers[-1].rstrip('.,').replace(',', '.')

    return ""

def clean_choice(choice: str) -> str:
    """Chuẩn hoá right_choice để so sánh."""
    return str(choice).lower().strip().rstrip('.,').replace(',', '.')

def normalize_column_for_dedup(val):
    val_str = str(val).strip()
    if val_str in ["nan", "[]", "['']", '[""]', ""]:
        return ""
    return val_str

def check_logic_match(ans_text: str, right_choice: str, choices_str: str) -> tuple[bool, str, str]:
    """
    Hàm kiểm tra ngữ nghĩa thông minh.
    Trả về (is_mismatch, extracted_val, right_val)
    """
    ans_text_lower = str(ans_text).lower()
    extracted = extract_answer(ans_text)
    cleaned_right = clean_choice(right_choice)

    if not cleaned_right or cleaned_right == "nan":
        return False, extracted, cleaned_right

    is_mismatch = True
    correct_content = ""

    # Trường hợp TRẮC NGHIỆM
    if cleaned_right in ['a', 'b', 'c', 'd'] and choices_str and normalize_column_for_dedup(choices_str):
        try:
            choices_list = ast.literal_eval(choices_str)
            for c in choices_list:
                c_str = str(c).lower().strip()
                if c_str.startswith(cleaned_right):
                    # Lọc sạch phần chữ cái đáp án (vd "b. 57312" -> "57312")
                    correct_content = re.sub(r'^[abcd][.:\s]+', '', c_str).strip()
                    break

            # Cứu vãn 1: Lời giải có nói rõ chọn đáp án đó
            if re.search(fr'(?:chọn|đáp án|khoanh|là)\s*(?:đáp án\s*)?{cleaned_right}\b', ans_text_lower):
                is_mismatch = False
            # Cứu vãn 2: Nội dung của đáp án xuất hiện rõ ràng trong phần cuối của lời giải (dùng \b để bắt chính xác whole word/number)
            elif correct_content and re.search(fr'\b{re.escape(correct_content)}\b', ans_text_lower[-max(50, len(correct_content)+20):]):
                is_mismatch = False
            # Cứu vãn 3: Nội dung của đáp án xuất hiện ở đâu đó và số sinh ra bằng nhau
            elif correct_content and (correct_content == extracted):
                is_mismatch = False

        except Exception:
            pass

    # Trường hợp TỰ LUẬN (hoặc sau khi check trắc nghiệm vẫn fail)
    if is_mismatch:
        if extracted == cleaned_right:
            is_mismatch = False
        elif correct_content and extracted == correct_content: # Dù right = 'b', nhưng extracted ra '57312'
            is_mismatch = False
        else:
            # Check giá trị số học tương đương (vd: 7000 == 7000.0)
            try:
                num_ext = float(extracted.replace(',', '.'))
                val_to_compare = correct_content if correct_content else cleaned_right
                num_right = float(val_to_compare.replace(',', '.'))
                if num_ext == num_right:
                    is_mismatch = False
            except ValueError:
                pass

    return is_mismatch, extracted, cleaned_right

def check_logic_match_llm_batch(batch_data: list, provider: str = "lm_studio") -> tuple[dict, str]:
    """
    Dùng LLM (Gemini hoặc LM Studio) để đối chiếu 1 batch các câu hỏi.
    Trả về một mảng chứa (Kết_quả_dict, Model_đã_dùng)
    """
    # Mặc định tất cả là mismatch (True) nếu có lỗi xảy ra
    results = {item['id']: True for item in batch_data}

    prompt = "Hãy kiểm tra danh sách các bài toán sau xem lời giải có dẫn đến đúng đáp án mục tiêu không.\n\n"
    for item in batch_data:
        prompt += f"[ID: {item['id']}]\nBài: {item['question']}\nGiải: {item['ans_text']}\nĐúng: {item['right_choice']}\n\n"

    prompt += "Quy định trả lời nghiêm ngặt:\n1. Mỗi bài 1 dòng bắt đầu bằng CHÍNH XÁC ID của bài toán đó.\n2. BẠN CHỈ ĐƯỢC IN RA 'YES' HOẶC 'NO'. TUYỆT ĐỐI KHÔNG IN RA ĐÁP ÁN (A, B, C, D) HAY KẾT QUẢ SỐ.\n3. Trả về dạng '[ID]: YES' (nếu lời giải logic và kết quả khớp) hoặc '[ID]: NO' (nếu sai lệch hoặc tính sai).\nĐừng bỏ sót bất kỳ ID nào.\nVí dụ:\n"
    prompt += "[456]: YES\n[457]: NO\n"

    actual_provider = provider
    content = ""

    try:
        if provider == "gemini" and GEMINI_API_KEY:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": "Bạn là Hệ thống chấm điểm tự động. Bắt buộc trả lời tất cả các bài được cung cấp, không được cắt ngang."}]},
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1000}
            }
            response = requests.post(url, json=payload, timeout=60)

            if response.status_code == 429:
                logger.warning("Gemini bị giới hạn Rate Limit (429). Tạm chuyển sang LM Studio cho batch này.")
                # Fallback to LM Studio
                return check_logic_match_llm_batch(batch_data, provider="lm_studio")

            response.raise_for_status()
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip().upper()

        else:
            actual_provider = "lm_studio"
            url = LM_STUDIO_URL
            payload = {
                "model": "gemma-4-e2b-it", # Bất kỳ model nào LM Studio đang load cũng sẽ nhận request này
                "messages": [
                    {"role": "system", "content": "Bạn là Hệ thống chấm điểm tự động. Bắt buộc trả lời tất cả các bài được cung cấp, không được cắt ngang."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0,
                "max_tokens": 1000
            }

            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip().upper()

        # Phân tích cú pháp trả về
        for item in batch_data:
            row_id = str(item['id'])

            if len(batch_data) == 1:
                if "YES" in content and "NO" not in content:
                    results[item['id']] = False
                    continue
                elif "NO" in content and "YES" not in content:
                    results[item['id']] = True
                    continue

            # Tìm pattern linh hoạt cho phép bao ngoặc [], {}, (), hoặc khoảng trắng, hoặc chữ ID
            match_yes = re.search(fr'(?:ID\s*:?\s*)?[\{{\[\(<]?\s*{re.escape(row_id)}\s*[\}}\]\)>]?\s*[:-]?\s*(YES)', content)
            match_no = re.search(fr'(?:ID\s*:?\s*)?[\{{\[\(<]?\s*{re.escape(row_id)}\s*[\}}\]\)>]?\s*[:-]?\s*(NO)', content)

            if match_yes and not match_no:
                results[item['id']] = False
            elif match_no and not match_yes:
                results[item['id']] = True
            elif match_yes and match_no:
                # Nếu có cả hai, lấy cái xuất hiện trước
                if match_yes.start() < match_no.start():
                    results[item['id']] = False
                else:
                    results[item['id']] = True
            else:
                logger.warning(f"[{actual_provider}] Không thể parse kết quả từ LLM cho ID {row_id}. Trả về góc: {content}")

    except Exception as e:
        logger.error(f"Lỗi gọi LLM Batch ({actual_provider}): {str(e)[:150]}")

    return results, actual_provider

def run_qa_level2():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    csv_path = os.path.join(project_root, "data_warehouse.csv")
    error_log_path = os.path.join(project_root, "qa_level2_errors.log")

    if not os.path.exists(csv_path):
        logger.error(f"Không tìm thấy file {csv_path}")
        return

    logger.info(f"Đọc dữ liệu từ {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        logger.error(f"Lỗi khi đọc file CSV: {str(e)}")
        return

    logger.info("Bắt đầu kiểm tra Semantic & Logic (QA Level 2)...")
    errors = []

    # 1. Kiểm tra trùng lặp (Deduplication)
    logger.info("- Đang kiểm tra trùng lặp ID và nội dung...")
    dup_ids = df[df.duplicated('id', keep=False)]
    if not dup_ids.empty:
        for val in dup_ids['id'].unique():
            errors.append(f"[Trùng lặp] ID '{val}' xuất hiện nhiều lần.")

    # Việc lặp lại chữ trong câu hỏi là bình thường (vd: "Thực hiện phép tính:", "Tìm x:", "Phát biểu nào sau đây đúng?")
    # Do đó, chỉ báo lỗi rò rỉ dữ liệu khi trùng lặp CẢ nội dung câu hỏi, LẪN các lựa chọn (choices), LẪN dữ liệu hình ảnh.
    dup_subset = ['question', 'choices', 'images_path']
    dup_quests = df[df.duplicated(subset=dup_subset, keep=False)]

    if not dup_quests.empty:
        # Clone DataFrame để tránh cảnh báo SettingWithCopyWarning của Pandas
        dup_quests = dup_quests.copy()
        # Chuẩn hoá các cột để tránh lỗi [] khác rỗng
        dup_quests.loc[:, 'choices_norm'] = dup_quests['choices'].apply(normalize_column_for_dedup)
        dup_quests.loc[:, 'images_norm'] = dup_quests['images_path'].apply(normalize_column_for_dedup)

        dup_subset_norm = ['question', 'choices_norm', 'images_norm']
        dup_grouped = dup_quests.groupby(dup_subset_norm).size()

        for keys, c in dup_grouped.items():
            if c > 1 and keys[0]: # có question
                q_short = str(keys[0]).replace('\n', ' ')[:50]
                has_img = keys[2] != ""
                has_ch = keys[1] != ""

                extra = []
                if has_img: extra.append(f"ảnh '{keys[2]}'")
                if has_ch: extra.append(f"choices '{keys[1]}'")
                extra_str = f" với cùng {' và '.join(extra)}" if extra else " (không có ảnh và không có choices)"

                errors.append(f"[Trùng lặp] Nội dung '{q_short}...'{extra_str} bị lặp lại {c} lần.")

    # 2. Kiểm tra tính đúng đắn & Chất lượng Text
    logger.info("- Đang kiểm tra Logic CoT và Chất lượng Text...")
    suspicious_items = []

    for index, row in df.iterrows():
        row_id = str(row.get("id", f"Row-{index}"))
        ans_text = str(row.get("answer", ""))
        right_choice = str(row.get("right_choice", ""))
        question = str(row.get("question", ""))
        choices_str = str(row.get("choices", ""))

        # 2a. Đối chiếu thông minh CoT (answer) với đáp án đích (right_choice)
        is_mismatch, extracted, cleaned_right = check_logic_match(ans_text, right_choice, choices_str)

        if is_mismatch:
            suspicious_items.append({
                "id": row_id, "question": question, "ans_text": ans_text,
                "right_choice": right_choice, "choices_str": choices_str,
                "extracted": extracted, "cleaned_right": cleaned_right
            })

        # 2b. Kiểm tra rác HTML, Encoding hoặc lỗi chữ
        if re.search(r'</?(?:div|span|p|br)[^>]*>', question):
            errors.append(f"[{row_id}] [Rác HTML] Câu hỏi chứa thẻ HTML chưa làm sạch: {question[:50]}...")

        if re.search(r'</?(?:div|span|p|br)[^>]*>', ans_text):
            errors.append(f"[{row_id}] [Rác HTML] Lời giải chứa thẻ HTML chưa làm sạch.")

        if "" in question or "" in ans_text:
            errors.append(f"[{row_id}] [Lỗi Font/Encoding] Dữ liệu chứa ký tự lỗi ().")

    # 3. Chấm các dòng nghi ngờ qua LLM theo batch
    if suspicious_items:
        batch_size = 5 # Dùng batch_size = 5 để cân bằng khả năng xử lý của cả Gemini và Local LM
        logger.info(f"Phát hiện {len(suspicious_items)} dòng nghi ngờ. Bắt đầu đưa qua LLM kiểm tra lại (Batch size = {batch_size})...")

        gemini_call_timestamps = []
        MAX_GEMINI_REQ_PER_MIN = 10 # Giới hạn 10 request / phút để tránh limit 15 req/min

        for i in range(0, len(suspicious_items), batch_size):
            batch = suspicious_items[i: i + batch_size]
            current_batch_num = (i // batch_size) + 1
            total_batches = (len(suspicious_items) + batch_size - 1) // batch_size

            # Dọn dẹp timestamps cũ hơn 60s
            current_time = time.time()
            gemini_call_timestamps = [t for t in gemini_call_timestamps if current_time - t < 60]

            # Quyết định dùng Gemini hay LM Studio dựa trên số request trong 1 phút qua
            if bool(GEMINI_API_KEY) and len(gemini_call_timestamps) < MAX_GEMINI_REQ_PER_MIN:
                provider = "gemini"
            else:
                provider = "lm_studio"

            if current_batch_num % 10 == 0 or current_batch_num == 1:
                logger.info(f"Đang gọi LLM batch {current_batch_num}/{total_batches} bằng {provider.upper()} ...")

            batch_results, actual_provider = check_logic_match_llm_batch(batch, provider=provider)

            # Cập nhật rate limit cho Gemini
            if actual_provider == "gemini":
                gemini_call_timestamps.append(time.time())
            elif provider == "gemini" and actual_provider == "lm_studio":
                # Nếu Gemini bị văng lỗi 429, đánh dấu full limit trong 60s tiếp theo luôn
                gemini_call_timestamps = [time.time()] * MAX_GEMINI_REQ_PER_MIN

            for item in batch:
                if batch_results.get(item['id'], True):
                    errors.append(f"[{item['id']}] [Bất đồng Logic] {actual_provider.upper()} xác nhận lời giải ra '{item['extracted']}' không khớp: '{item['cleaned_right']}'")

            # Giảm đáng kể thời gian chờ giữa các vòng lặp vì LM Studio tự xếp hàng request
            time.sleep(0.01)

    # Kết xuất kết quả
    if errors:
        logger.error(f"Phát hiện {len(errors)} vấn đề logic/ngữ nghĩa (Level 2):")

        # Lưu log
        with open(error_log_path, "w", encoding="utf-8") as f:
            for err in errors:
                f.write(err + "\n")
        logger.info(f"Đã xuất toàn bộ chi tiết {len(errors)} vấn đề ra file: {error_log_path}")

        for err in errors[:30]:
            logger.error(err)
        if len(errors) > 30:
            logger.error(f"... và {len(errors) - 30} vấn đề khác (vui lòng xem file log).")
    else:
        logger.info("Dữ liệu Level 2 hoàn hảo! Không phát hiện lỗi logic, trùng lặp hay văn bản rác.")

if __name__ == "__main__":
    run_qa_level2()
