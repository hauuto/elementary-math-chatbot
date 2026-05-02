from __future__ import annotations

import argparse
import ast
import concurrent.futures as cf
import csv
import json
import logging
import math
import shutil
import datetime
import random
import re
import time
import sys
from pathlib import Path
from typing import Any

from PIL import Image
import google.generativeai as genai  # type: ignore[import-not-found]
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(SCRIPTS_DIR / ".env", override=False)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import GEMINI_API_KEY, GEMINI_MODEL_ID  # noqa: E402


LOGGER = logging.getLogger("augment_questions")
DEFAULT_INPUT_FILE = PROJECT_ROOT / "data_warehouse.csv"
DEFAULT_OUTPUT_FILE = DEFAULT_INPUT_FILE
DEFAULT_SEED_SAMPLES = 7500
DEFAULT_AUGMENTS_PER_SEED = 5
DEFAULT_RANDOM_SEED = 42
DEFAULT_REQUEST_TIMEOUT = 120
DEFAULT_QUESTIONS_PER_CALL = 4
DEFAULT_WORKERS = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Randomly augment elementary math questions with Gemini."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_FILE,
        help="Input CSV file containing the source questions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Output CSV file. Defaults to the input file for in-place append.",
    )
    parser.add_argument(
        "--seed-samples",
        type=int,
        default=DEFAULT_SEED_SAMPLES,
        help="Number of random source questions to use as seeds.",
    )
    parser.add_argument(
        "--augments-per-seed",
        type=int,
        default=DEFAULT_AUGMENTS_PER_SEED,
        help="Number of new questions to create from each seed.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Random seed for deterministic sampling.",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default=GEMINI_MODEL_ID,
        help="Gemini model to use for generation.",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="Timeout in seconds for each Gemini request.",
    )
    parser.add_argument(
        "--questions-per-call",
        type=int,
        default=DEFAULT_QUESTIONS_PER_CALL,
        help="How many questions Gemini should generate per API call.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Number of parallel worker threads for Gemini calls.",
    )
    parser.add_argument(
        "--renumber-only",
        action="store_true",
        help="Only renumber the input CSV ids from 1 and exit without generating new rows.",
    )
    parser.add_argument(
        "--fill-missing",
        action="store_true",
        help="Use Gemini to fill missing answer-related fields in the CSV and rewrite it in place.",
    )
    parser.add_argument(
        "--fill-batch-size",
        type=int,
        default=5,
        help="Number of rows to request fills for in a single Gemini call (batch size).",
    )
    return parser.parse_args()


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def parse_list_cell(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    value = raw_value.strip()
    if not value:
        return []
    normalized = value.replace("'", '"')
    if normalized in {"[]", "[\"\"]"}:
        return []
    try:
        decoded = json.loads(value)
    except Exception:  # noqa: BLE001
        return [item.strip() for item in re.split(r"\s*,\s*", value) if item.strip()]
    if isinstance(decoded, list):
        return [str(item) for item in decoded if str(item).strip()]
    return []


def serialize_list_cell(values: list[str]) -> str:
    import json

    return json.dumps(values, ensure_ascii=False)


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split())


def normalize_markdown_block(value: str | None) -> str:
    text = (value or "").replace("\r\n", "\n").strip()
    return text


def cell_is_missing(row: dict[str, str], field_name: str) -> bool:
    value = row.get(field_name)
    if field_name in {"choices", "images_path"}:
        return len(parse_list_cell(value)) == 0
    return not normalize_text(value)


def renumber_rows_sequentially(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    renumbered_rows: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        updated_row = dict(row)
        updated_row["id"] = str(index)
        renumbered_rows.append(updated_row)
    return renumbered_rows


def get_next_id(rows: list[dict[str, str]]) -> int:
    numeric_ids = []
    for row in rows:
        try:
            numeric_ids.append(int(str(row.get("id", "0")).strip()))
        except ValueError:
            continue
    return max(numeric_ids, default=0) + 1


def parse_csv_table(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            raw_fieldnames = next(reader)
        except StopIteration:
            return [], []

        cleaned_fieldnames = [name.lstrip("\ufeff").strip() for name in raw_fieldnames if name.strip()]
        fieldnames = dedupe_preserve_order([name for name in cleaned_fieldnames if name])
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            if not raw_row:
                continue
            row: dict[str, str] = {}
            for index, fieldname in enumerate(raw_fieldnames):
                cleaned_fieldname = fieldname.lstrip("\ufeff").strip()
                if not cleaned_fieldname:
                    continue
                value = raw_row[index] if index < len(raw_row) else ""
                if cleaned_fieldname not in row:
                    row[cleaned_fieldname] = value
            normalized_row = {fieldname: row.get(fieldname, "") for fieldname in fieldnames}
            rows.append(normalized_row)
    return rows, fieldnames


def rewrite_csv_table(csv_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(csv_path)


def append_csv_row(csv_path: Path, row: dict[str, str], fieldnames: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if is_new_file:
            writer.writeheader()
        writer.writerow(row)


def append_csv_rows(csv_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if is_new_file:
            writer.writeheader()
        writer.writerows(rows)


def load_images(image_paths: list[str]) -> list[Image.Image]:
    images: list[Image.Image] = []
    for image_path in image_paths:
        resolved_path = (PROJECT_ROOT / image_path).resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Image not found: {resolved_path}")
        with Image.open(resolved_path) as image:
            images.append(image.convert("RGB"))
    return images


def create_model(model_id: str) -> genai.GenerativeModel:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(model_id)


def generate_raw_markdown_with_gemini(
    model: genai.GenerativeModel,
    prompt: str,
    images: list[Image.Image] | None = None,
    temperature: float = 0.7,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
) -> str:
    payload: list[Any] = [prompt]
    if images:
        payload.extend(images)
    try:
        response = model.generate_content(
            payload,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": 1024,
            },
            request_options={"timeout": request_timeout},
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Gemini request failed: {exc}") from exc
    if not getattr(response, "text", None):
        raise RuntimeError("Gemini returned an empty response")
    return response.text


def build_generation_prompt(row: dict[str, str], use_image: bool, questions_per_call: int) -> str:
    choices = parse_list_cell(row.get("choices"))
    choices_text = "\n".join(f"- {choice}" for choice in choices) if choices else "-"
    
    prompt = (
        "Bạn là một chuyên gia giáo dục và thiết kế bài tập Toán Tiểu học tại Việt Nam. "
        f"Nhiệm vụ của bạn là sinh ra {questions_per_call} bài toán mới từ mẫu gốc để huấn luyện AI. "
        "Hãy tuân thủ nghiêm ngặt các nguyên tắc sau:\n"
        "1. Đa dạng hóa bối cảnh: Thay đổi tên nhân vật (thuần Việt), đồ vật, tạo tình huống thực tế, sinh động.\n"
        "2. Chuỗi mức độ từ Dễ đến Khó: Các bài toán sinh ra PHẢI được sắp xếp theo mức độ khó tăng dần. "
        f"ITEM 1 là bài dễ nhất (cơ bản, ít dữ kiện, dễ nhẩm). Các ITEM tiếp theo tăng dần độ phức tạp (thêm bước tính, yêu cầu tư duy sâu hơn, lật ngược vấn đề), cho đến ITEM {questions_per_call} là bài khó nhất.\n"
        "3. Tính hợp lý: Số liệu phải thực tế. Kết quả tính toán không ra số âm, số thập phân (nếu là lớp dưới), và đồ vật không bị chia cắt vô lý.\n"
        "4. Định dạng Markdown trực quan & Văn phong sư phạm: Sử dụng triệt để Markdown (`**in đậm**`, `*in nghiêng*`, danh sách bullet `-`) để bài toán và lời giải hiển thị trực quan, đẹp mắt trên trình duyệt. Trong phần ANSWER, tuyệt đối không lặp lại một khuôn mẫu; hãy luân phiên thay đổi phong cách giảng (từ truyền thống, phân tích từng bước, đến đối thoại khích lệ).\n"
        "5. Trắc nghiệm chất lượng (Nếu có): Các đáp án sai (bẫy) phải mô phỏng chính xác các lỗi tư duy phổ biến của trẻ (như cộng quên nhớ, tính nhầm thứ tự).\n"
        "6. Output Format: Chỉ trả về raw text. KHÔNG dùng markdown code block (```) bọc toàn bộ đầu ra để tránh lỗi parse, nhưng HÃY dùng markdown bên trong nội dung từng phần. KHÔNG viết lời dẫn.\n\n"
        "--- DỮ LIỆU GỐC ---\n"
        f"Câu hỏi gốc: {normalize_text(row.get('question'))}\n"
        f"Lựa chọn gốc: {choices_text}\n"
    )
    
    if use_image:
        prompt += (
            "Ngữ cảnh ảnh đính kèm: Bám sát các dữ kiện trực quan trong ảnh (số lượng, đối tượng). "
            "Bạn có thể thay đổi cách đặt câu hỏi hoặc thêm điều kiện giả định dựa trên ảnh để phát triển bài toán.\n"
        )
    else:
        prompt += (
            "Ngữ cảnh văn bản: Đổi mới hoàn toàn chủ đề so với câu gốc để làm phong phú dữ liệu, nhưng giữ sự liên kết về dạng toán cốt lõi.\n"
        )

    prompt += (
        "\n--- BẮT BUỘC XUẤT RA THEO CÁC MỤC SAU ---\n"
        f"Hãy tạo đúng {questions_per_call} bài toán từ dễ đến khó. Trình bày mỗi bài theo chuẩn sau (tăng dần số thứ tự ITEM):\n\n"
        "## ITEM 1\n"
        "### QUESTION\n"
        "<Nội dung câu hỏi. Không có bất kỳ markdown nào>\n\n"
        "### CHOICES\n"
        "<Nếu là tự luận: -> >\n"
        "<Nếu trắc nghiệm: Ghi 4 dòng bắt đầu bằng '- A. ', '- B. ', '- C. ', '- D. '>\n\n"
        "### ANSWER\n"
        "<Trình bày lời giải sư phạm bằng markdown trực quan. Ví dụ: Dùng gạch đầu dòng (`-`) cho các bước lập luận, in đậm (**...**) các phép tính và kết quả. Đổi mới phong cách trình bày liên tục giữa các ITEM. Luôn có phần '**Đáp số:**' rõ ràng ở cuối.>\n\n"
        "### RIGHT_CHOICE\n"
        "<Đáp án cuối cùng hoặc chữ cái A/B/C/D>\n\n"
        "Tuyệt đối không được trộn các item vào nhau và không thêm mục khác ngoài các heading trên.\n"
    )
        
    return prompt


def build_fill_prompt(row: dict[str, str], missing_fields: list[str], use_image: bool) -> str:
    choices = parse_list_cell(row.get("choices"))
    choices_text = "\n".join(f"- {choice}" for choice in choices) if choices else "-"
    prompt = (
        "Bạn là giáo viên Toán Tiểu học. Hãy điền chính xác các trường còn thiếu cho một mẫu dữ liệu bài toán theo văn phong sư phạm, chỉ được xưng bạn và tôi, nhưng phải trả lời như 1 người thầy. "
        "Chỉ trả về theo các heading bên dưới, không dùng JSON, không dùng code block, không thêm lời dẫn. "
        "Nếu ảnh quá mờ, thiếu chi tiết, hoặc không đủ dữ kiện để suy ra bài toán thì phải trả về trạng thái không giải được.\n\n"
        "### QUESTION\n"
        "<nếu không đủ dữ kiện, để trống, câu hỏi không cần sửa lại>\n\n"
        "### CHOICES\n"
        "<nếu choices đang thiếu thì tạo 4 lựa chọn; nếu tự luận thì ghi ->; nếu không thiếu thì giữ nguyên hoặc bỏ qua>\n\n"
        "### ANSWER\n"
        "<điền lời giải rõ ràng, chi tiết bằng tiếng Việt. Với các bài toán đặt tính rồi tính thì cũng phải hiển thị markdown cho hợp lý>\n\n"
        "### RIGHT_CHOICE\n"
        "<điền đáp số cuối cùng hoặc chữ cái A/B/C/D nếu là trắc nghiệm>\n\n"
        "### INSTRUCTION\n"
        "<điền instruction tiếng Việt ngắn gọn nếu đang thiếu>\n\n"
        "### STATUS\n"
        "<OK hoặc UNRESOLVABLE: <lý do ngắn gọn nếu ảnh mờ/không đủ dữ kiện>>\n\n"
        f"Trường cần điền: {', '.join(missing_fields)}\n"
        f"Câu hỏi hiện có: {normalize_text(row.get('question'))}\n"
        f"Lựa chọn hiện có: {choices_text}\n"
        f"Lời giải hiện có: {normalize_markdown_block(row.get('answer'))}\n"
        f"Đáp án hiện có: {normalize_text(row.get('right_choice'))}\n"
        f"Instruction hiện có: {normalize_text(row.get('instruction'))}\n"
    )
    if use_image:
        prompt += (
            "Có ảnh đính kèm, hãy dùng ảnh làm ngữ cảnh để điền bù các trường còn thiếu.\n"
        )
    return prompt


def parse_markdown_sections(markdown_text: str) -> dict[str, str]:
    section_names = {"QUESTION", "CHOICES", "ANSWER", "RIGHT_CHOICE", "INSTRUCTION", "STATUS"}
    sections: dict[str, list[str]] = {name: [] for name in section_names}
    current_section: str | None = None

    for raw_line in markdown_text.replace("\r\n", "\n").split("\n"):
        heading_match = re.match(r"^###\s+(QUESTION|CHOICES|ANSWER|RIGHT_CHOICE|INSTRUCTION|STATUS)\s*$", raw_line.strip(), flags=re.IGNORECASE)
        if heading_match:
            current_section = heading_match.group(1).upper()
            continue
        if current_section:
            sections[current_section].append(raw_line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def parse_choices_block(block: str) -> list[str]:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines or lines == ["->"]:
        return [""]

    if len(lines) == 1 and lines[0].startswith("[") and lines[0].endswith("]"):
        try:
            parsed = ast.literal_eval(lines[0])
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()] or [""]

    choices: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^[-*+]\s*", "", line).strip()
        if cleaned in {"->", "-", "—", ""}:
            continue
        choices.append(cleaned)
    return choices or [""]


def fill_missing_fields_for_row(
    model: genai.GenerativeModel,
    row: dict[str, str],
    request_timeout: int,
) -> tuple[dict[str, str], str]:
    missing_fields = [
        field
        for field in ["question", "answer", "right_choice", "choices", "instruction"]
        if cell_is_missing(row, field) and field in row
    ]
    if not missing_fields:
        return row, "OK"

    image_paths = parse_list_cell(row.get("images_path"))
    images = load_images(image_paths) if image_paths else []
    use_image = bool(images)

    if not normalize_text(row.get("question")) and not use_image:
        # If the question is missing and no image is available, mark as invalid and ask user to resend
        return row, "INVALID_QUESTION: missing — please provide the question text or an image"

    markdown_response = generate_raw_markdown_with_gemini(
        model=model,
        prompt=build_fill_prompt(row, missing_fields, use_image=use_image),
        images=images if use_image else None,
        request_timeout=request_timeout,
    )
    sections = parse_markdown_sections(markdown_response)
    status = normalize_text(sections.get("STATUS", "OK")) or "OK"

    if status.upper().startswith("UNRESOLVABLE"):
        return row, status

    updated_row = dict(row)
    if cell_is_missing(updated_row, "choices") and sections.get("CHOICES"):
        updated_row["choices"] = serialize_list_cell(parse_choices_block(sections.get("CHOICES", "")))
    if cell_is_missing(updated_row, "answer") and sections.get("ANSWER"):
        updated_row["answer"] = normalize_markdown_block(sections.get("ANSWER", ""))
    if cell_is_missing(updated_row, "right_choice") and sections.get("RIGHT_CHOICE"):
        updated_row["right_choice"] = normalize_text(sections.get("RIGHT_CHOICE", ""))
    if cell_is_missing(updated_row, "instruction") and sections.get("INSTRUCTION"):
        updated_row["instruction"] = normalize_text(sections.get("INSTRUCTION", ""))
    if cell_is_missing(updated_row, "question") and sections.get("QUESTION"):
        updated_row["question"] = normalize_text(sections.get("QUESTION", ""))

    return updated_row, status


def build_fill_batch_prompt(rows: list[dict[str, str]], use_images_list: list[bool]) -> str:
    prompt = (
        "Bạn là giáo viên Toán Tiểu học. Hãy điền các trường còn thiếu cho mỗi ITEM dưới đây. "
        "Trả về raw text, không dùng JSON, không dùng code block, không thêm lời dẫn. \n\n"
    )
    for i, row in enumerate(rows, start=1):
        choices = parse_list_cell(row.get("choices"))
        choices_text = "\n".join(f"- {c}" for c in choices) if choices else "-"
        prompt += f"## ITEM {i}\n"
        prompt += f"Câu hỏi hiện có: {normalize_text(row.get('question'))}\n"
        prompt += f"Lựa chọn hiện có:\n{choices_text}\n"
        prompt += f"Lời giải hiện có: {normalize_markdown_block(row.get('answer'))}\n"
        prompt += f"Đáp án hiện có: {normalize_text(row.get('right_choice'))}\n"
        prompt += "\n"
    prompt += (
        "CHO DANG XUAT: Với mỗi ITEM, hãy trả về các heading sau (chỉ những heading):\n"
        "### QUESTION\n### CHOICES\n### ANSWER\n### RIGHT_CHOICE\n### INSTRUCTION\n### STATUS\n"
    )
    prompt += (
        "\nNếu ảnh đính kèm cho ITEM nào thì dùng thông tin ảnh để suy luận; nếu không đủ dữ kiện, trả về STATUS: UNRESOLVABLE: <lý do ngắn>."
    )
    prompt += (
        "\nNếu đề bài bị sai, mâu thuẫn, hoặc câu hỏi thiếu dữ kiện (không thể suy ra được kết quả), hãy trả về `STATUS: INVALID_QUESTION: <lý do ngắn>`, và trong phần ANSWER ghi một dòng ngắn yêu cầu người dùng gửi lại đề bài đúng hoặc bổ sung ảnh/thông tin."
    )
    return prompt


def fill_missing_rows_in_place(
    csv_path: Path,
    model: genai.GenerativeModel,
    request_timeout: int,
    workers: int,
    batch_size: int = 5,
) -> None:
    # create a backup before making in-place edits
    backup_path = csv_path.with_suffix(csv_path.suffix + f".bak.{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
    try:
        shutil.copy2(csv_path, backup_path)
        LOGGER.info("Backup of %s created at %s", csv_path, backup_path)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to create backup of %s: %s", csv_path, exc)

    rows, fieldnames = parse_csv_table(csv_path)
    fieldnames = ensure_fieldnames(fieldnames)

    rows_to_update: list[tuple[int, dict[str, str]]] = []
    for index, row in enumerate(rows):
        # Only enqueue rows that are missing the `answer` field to minimize API usage.
        if cell_is_missing(row, "answer"):
            rows_to_update.append((index, row))

    if not rows_to_update:
        LOGGER.info("No rows with missing 'answer' found in %s", csv_path)
        return

    LOGGER.info("Filling %d rows (missing 'answer') in %s", len(rows_to_update), csv_path)

    def fill_batch_task(batch_items: list[tuple[int, dict[str, str]]]) -> list[tuple[int, dict[str, str], str]]:
        # batch_items: list of (index, row)
        batch_indices = [item[0] for item in batch_items]
        batch_rows = [item[1] for item in batch_items]
        images_lists = [parse_list_cell(r.get("images_path")) for r in batch_rows]
        use_images_list = [bool(il) for il in images_lists]

        retries = 0
        while True:
            try:
                prompt = build_fill_batch_prompt(batch_rows, use_images_list)
                # collect images in order if any; gemini supports multiple images in payload
                images_payload = []
                for img_list in images_lists:
                    if img_list:
                        try:
                            images_payload.append(load_images(img_list)[0])
                        except Exception:
                            images_payload.append(None)

                images_arg = [img for img in images_payload if img is not None] or None

                md = generate_raw_markdown_with_gemini(
                    model=model,
                    prompt=prompt,
                    images=images_arg,
                    request_timeout=request_timeout,
                )
                # allow fewer items; we'll accept what we get and mark the rest UNRESOLVABLE
                item_blocks = split_batch_items(md, len(batch_rows), allow_less=True)
                results: list[tuple[int, dict[str, str], str]] = []
                for idx, block in enumerate(item_blocks):
                    sections = parse_markdown_sections(block)
                    status = normalize_text(sections.get("STATUS", "OK")) or "OK"
                    updated_row = dict(batch_rows[idx])
                    if status.upper().startswith("UNRESOLVABLE"):
                        results.append((batch_indices[idx], updated_row, status))
                        continue
                    if cell_is_missing(updated_row, "choices") and sections.get("CHOICES"):
                        updated_row["choices"] = serialize_list_cell(parse_choices_block(sections.get("CHOICES", "")))
                    if cell_is_missing(updated_row, "answer") and sections.get("ANSWER"):
                        updated_row["answer"] = normalize_markdown_block(sections.get("ANSWER", ""))
                    if cell_is_missing(updated_row, "right_choice") and sections.get("RIGHT_CHOICE"):
                        updated_row["right_choice"] = normalize_text(sections.get("RIGHT_CHOICE", ""))
                    if cell_is_missing(updated_row, "instruction") and sections.get("INSTRUCTION"):
                        updated_row["instruction"] = normalize_text(sections.get("INSTRUCTION", ""))
                    if cell_is_missing(updated_row, "question") and sections.get("QUESTION"):
                        updated_row["question"] = normalize_text(sections.get("QUESTION", ""))
                    results.append((batch_indices[idx], updated_row, status))

                # For any rows not addressed by the model, mark as UNRESOLVABLE so we don't keep retrying forever
                if len(item_blocks) < len(batch_rows):
                    for j in range(len(item_blocks), len(batch_rows)):
                        results.append((batch_indices[j], dict(batch_rows[j]), "UNRESOLVABLE: insufficient items returned"))
                    LOGGER.warning("Gemini returned %d/%d items for batch starting id=%s; marking remaining as UNRESOLVABLE", len(item_blocks), len(batch_rows), batch_rows[0].get("id", ""))

                # if no items at all, fall back to per-row single-fill attempts to salvage where possible
                if len(item_blocks) == 0:
                    if retries < 2:
                        LOGGER.warning("Gemini returned 0 items for batch starting id=%s; falling back to per-row fills (retry %d)", batch_rows[0].get("id", ""), retries + 1)
                        single_results = []
                        for idx2, single_row in enumerate(batch_rows):
                            try:
                                updated_row, status = fill_missing_fields_for_row(model, single_row, request_timeout)
                                single_results.append((batch_indices[idx2], updated_row, status))
                            except Exception as exc:
                                single_results.append((batch_indices[idx2], single_row, f"ERROR: {exc}"))
                        return single_results
                    else:
                        LOGGER.warning("Batch starting at id=%s failed after 3 retries: Gemini returned 0 items", batch_items[0][1].get("id", ""))
                        return [(item[0], item[1], "ERROR: Gemini returned 0 items") for item in batch_items]

                return results
            except Exception as exc:  # noqa: BLE001
                retries += 1
                if retries >= 3:
                    LOGGER.warning("Batch starting at id=%s failed after 3 retries: %s", batch_items[0][1].get("id", ""), exc)
                    # return original rows with error status
                    return [(item[0], item[1], f"ERROR: {exc}") for item in batch_items]
                LOGGER.warning("Retrying batch starting at id=%s after error: %s", batch_items[0][1].get("id", ""), exc)
                time.sleep(1)

    completed_rows = list(rows)
    # Use thread pool to process batches; persist each completed row immediately
    batches: list[list[tuple[int, dict[str, str]]]] = []
    for i in range(0, len(rows_to_update), batch_size):
        batches.append(rows_to_update[i : i + batch_size])

    with cf.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fill_batch_task, batch): batch for batch in batches}
        for future in cf.as_completed(futures):
            batch_results = future.result()
            for index, updated_row, status in batch_results:
                completed_rows[index] = updated_row
                try:
                    rewrite_csv_table(csv_path, completed_rows, fieldnames)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("Failed to persist CSV after updating id=%s: %s", updated_row.get("id", ""), exc)

                if status and status.upper().startswith("UNRESOLVABLE"):
                    LOGGER.warning("UNRESOLVABLE for row id=%s: %s", updated_row.get("id", ""), status)
                elif status and status.startswith("ERROR"):
                    LOGGER.warning("ERROR filling row id=%s: %s", updated_row.get("id", ""), status)
                else:
                    LOGGER.info("Updated row id=%s: %s", updated_row.get("id", ""), status)

    LOGGER.info("Finished filling missing fields for %s", csv_path)


def split_batch_items(markdown_text: str, expected_items: int, allow_less: bool = False) -> list[str]:
    pattern = re.compile(r"(?m)^##\s+ITEM\s+\d+\s*$")
    matches = list(pattern.finditer(markdown_text))
    if not allow_less and len(matches) < expected_items:
        raise RuntimeError(f"Gemini returned {len(matches)} items, expected {expected_items}")

    item_blocks: list[str] = []
    # if matches is empty, return empty list
    for index, match in enumerate(matches[:expected_items]):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        item_blocks.append(markdown_text[start:end].strip())
    return item_blocks


def build_augmented_rows(
    model: genai.GenerativeModel,
    seed_row: dict[str, str],
    request_timeout: int,
    questions_per_call: int,
    temperature: float = 0.7,
) -> list[dict[str, str]]:
    image_paths = parse_list_cell(seed_row.get("images_path"))
    images = load_images(image_paths) if image_paths else []
    use_image = bool(images)

    markdown_response = generate_raw_markdown_with_gemini(
        model=model,
        prompt=build_generation_prompt(seed_row, use_image=use_image, questions_per_call=questions_per_call),
        images=images if use_image else None,
        temperature=temperature,
        request_timeout=request_timeout,
    )

    LOGGER.debug("Gemini response length: %d chars", len(markdown_response))
    # Allow partial responses (allow_less=True) so we can salvage what Gemini did return
    item_blocks = split_batch_items(markdown_response, questions_per_call, allow_less=True)
    LOGGER.debug("Parsed %d item blocks from Gemini response", len(item_blocks))
    
    if len(item_blocks) == 0:
        LOGGER.warning("Gemini returned 0 parseable items for seed id=%s; response preview: %s", seed_row.get("id", ""), markdown_response[:200])
        raise RuntimeError("Gemini returned 0 parseable items")
    
    augmented_rows: list[dict[str, str]] = []
    for idx, block in enumerate(item_blocks):
        sections = parse_markdown_sections(block)
        question = normalize_text(sections.get("QUESTION", ""))
        answer = normalize_markdown_block(sections.get("ANSWER", ""))
        right_choice = normalize_text(sections.get("RIGHT_CHOICE", ""))
        choices = parse_choices_block(sections.get("CHOICES", ""))

        if not question:
            LOGGER.warning("Item %d missing question from seed id=%s; skipping", idx + 1, seed_row.get("id", ""))
            continue
        if not answer:
            LOGGER.warning("Item %d missing answer from seed id=%s; skipping", idx + 1, seed_row.get("id", ""))
            continue

        augmented_rows.append(
            {
                "id": "",
                "question": question,
                "answer": answer,
                "right_choice": right_choice,
                "choices": serialize_list_cell(choices),
                "instruction": normalize_text(seed_row.get("instruction")),
                "images_path": serialize_list_cell(image_paths),
                "split_origin": f"augmentation:{seed_row.get('id', '')}",
            }
        )
    
    LOGGER.debug("Built %d valid augmented rows from seed id=%s", len(augmented_rows), seed_row.get("id", ""))
    return augmented_rows


def ensure_fieldnames(fieldnames: list[str]) -> list[str]:
    required = [
        "id",
        "question",
        "answer",
        "right_choice",
        "choices",
        "instruction",
        "images_path",
        "split_origin",
    ]
    if fieldnames:
        ordered = dedupe_preserve_order([name for name in fieldnames if name])
        for column in required:
            if column not in ordered:
                ordered.append(column)
        return ordered
    return required


def normalize_existing_output(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return [], []
    rows, fieldnames = parse_csv_table(csv_path)
    normalized_fieldnames = ensure_fieldnames(fieldnames)
    if normalized_fieldnames != fieldnames:
        LOGGER.info("Normalizing existing CSV header at %s", csv_path)
        rewrite_csv_table(csv_path, rows, normalized_fieldnames)
    return rows, normalized_fieldnames


def renumber_file_in_place(csv_path: Path) -> None:
    rows, fieldnames = parse_csv_table(csv_path)
    if not rows:
        raise RuntimeError(f"No rows found in {csv_path}")
    normalized_fieldnames = ensure_fieldnames(fieldnames)
    renumbered_rows = renumber_rows_sequentially(rows)
    rewrite_csv_table(csv_path, renumbered_rows, normalized_fieldnames)
    LOGGER.info("Renumbered %d rows in %s", len(renumbered_rows), csv_path)


def batch_seed_rows(seed_rows: list[dict[str, str]], batch_count: int) -> list[dict[str, str]]:
    if not seed_rows:
        return []
    return [seed_rows[index % len(seed_rows)] for index in range(batch_count)]


def main() -> int:
    setup_logging()
    args = parse_args()

    if args.seed_samples <= 0 or args.augments_per_seed <= 0:
        raise ValueError("seed-samples and augments-per-seed must be positive integers")

    LOGGER.info("Loading CSV from %s", args.input)
    rows, fieldnames = parse_csv_table(args.input)
    fieldnames = ensure_fieldnames(fieldnames)
    if not rows:
        raise RuntimeError("Input CSV is empty")

    if args.renumber_only:
        renumber_file_in_place(args.output if args.input.resolve() == args.output.resolve() else args.input)
        return 0

    if args.fill_missing:
        target_path = args.output if args.input.resolve() == args.output.resolve() else args.input
        model = create_model(args.model_id)
        fill_missing_rows_in_place(
            target_path,
            model,
            args.request_timeout,
            args.workers,
            batch_size=args.fill_batch_size,
        )
        return 0

    if args.input.resolve() == args.output.resolve():
        rows = renumber_rows_sequentially(rows)
        rewrite_csv_table(args.output, rows, fieldnames)

    rng = random.Random(args.random_seed)
    seed_count = min(args.seed_samples, len(rows))
    seeds = rng.sample(rows, seed_count)

    target_augmentations = args.seed_samples * args.augments_per_seed
    batch_count = math.ceil(target_augmentations / args.questions_per_call)
    batch_sources = batch_seed_rows(seeds, batch_count)

    LOGGER.info("Selected %d seed rows", len(seeds))
    model = create_model(args.model_id)

    next_id = len(rows) + 1
    created = 0

    def generate_batch(batch_index: int, seed_row: dict[str, str]) -> tuple[int, list[dict[str, str]]]:
        # Random temperature between 0.5 and 0.9 for diversity
        batch_temperature = random.uniform(0.5, 0.9)
        LOGGER.info("Generating batch %d/%d from seed id=%s (temperature=%.2f)", batch_index, batch_count, seed_row.get("id", ""), batch_temperature)
        retries = 0
        while True:
            try:
                batch_rows = build_augmented_rows(
                    model,
                    seed_row,
                    args.request_timeout,
                    args.questions_per_call,
                    temperature=batch_temperature,
                )
                LOGGER.info("Batch %d generated %d rows from seed id=%s", batch_index, len(batch_rows), seed_row.get("id", ""))
                return batch_index, batch_rows
            except Exception as exc:  # noqa: BLE001
                retries += 1
                if retries >= 3:
                    LOGGER.error("Failed to generate batch %d from seed id=%s after 3 retries: %s", batch_index, seed_row.get("id", ""), exc)
                    # Return empty batch instead of raising; we'll handle empty batches gracefully
                    return batch_index, []
                LOGGER.warning("Retrying batch %d after error: %s", batch_index, exc)
                time.sleep(1)

    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(generate_batch, index + 1, seed_row) for index, seed_row in enumerate(batch_sources)]
        for future in cf.as_completed(futures):
            batch_index, batch_rows = future.result()
            LOGGER.debug("Batch %d completed with %d rows", batch_index, len(batch_rows))
            remaining = target_augmentations - created
            if remaining <= 0:
                LOGGER.debug("Already created %d augmentations, skipping batch %d", created, batch_index)
                continue
            rows_to_write = batch_rows[:remaining]
            if not rows_to_write:
                LOGGER.warning("Batch %d returned 0 rows, skipping", batch_index)
                continue
            for row in rows_to_write:
                row["id"] = str(next_id)
                next_id += 1
                for column in fieldnames:
                    row.setdefault(column, "")
                # write each row immediately and log status per-row
                append_csv_row(args.output, row, fieldnames)
                created += 1
                LOGGER.info("ADDED id=%s split_origin=%s (batch=%d)", row.get("id", ""), row.get("split_origin", ""), batch_index)
            LOGGER.info("Committed batch %d with %d rows (%d/%d)", batch_index, len(rows_to_write), created, target_augmentations)

    LOGGER.info(
        "Done. Seeds: %d, Augmentations: %d, Output file: %s",
        len(seeds),
        created,
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())