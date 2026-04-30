from __future__ import annotations

import ast
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from .config import GEMINI_API_KEY, GEMINI_BATCH_SIZE, GEMINI_MODEL, IMAGE_DIR, ROOT_DIR
from .csv_store import _WRITE_LOCK, next_id, normalize_row, read_records, write_records
from .schemas import ImportResponse

IMAGE_COLUMNS = ("images_path", "image_paths", "image_path", "image")
FINAL_ANSWER_PATTERN = re.compile(r"####\s*(.+)\s*$", re.MULTILINE)


def import_parquet_file(file_content: bytes, filename: str, split_origin: str, translate: bool, fill_missing: bool) -> ImportResponse:
    warnings: list[str] = []
    source = split_origin.strip() or Path(filename).stem or "parquet_upload"

    if (translate or fill_missing) and not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY chưa được cấu hình trên VPS.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as temp_file:
        temp_file.write(file_content)
        parquet_path = Path(temp_file.name)

    try:
        frame = pd.read_parquet(parquet_path)
    finally:
        parquet_path.unlink(missing_ok=True)

    missing_columns = {"question", "answer"} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"File parquet thiếu cột: {', '.join(sorted(missing_columns))}")

    new_records: list[dict[str, str]] = []
    skipped = 0
    for _, row in frame.iterrows():
        question = clean_text(row.get("question"))
        answer = clean_text(row.get("answer"))
        if not question and not answer:
            skipped += 1
            continue
        images = copy_images_from_row(row.to_dict(), warnings)
        new_records.append(
            normalize_row(
                {
                    "question": question,
                    "answer": answer,
                    "right_choice": extract_right_choice(answer),
                    "choices": "[]",
                    "instruction": source,
                    "images_path": repr(images),
                    "split_origin": source,
                }
            )
        )

    if translate and new_records:
        translate_records(new_records)

    updated_existing = 0
    with _WRITE_LOCK:
        records = read_records()
        if fill_missing:
            updated_existing = fill_missing_records(records)

        current_id = next_id(records)
        for record in new_records:
            record["id"] = str(current_id)
            current_id += 1
            records.append(record)

        write_records(records)

    return ImportResponse(added=len(new_records), updated_existing=updated_existing, skipped=skipped, warnings=warnings)


def clean_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def extract_right_choice(answer: str) -> str:
    match = FINAL_ANSWER_PATTERN.search(answer)
    return match.group(1).strip() if match else ""


def copy_images_from_row(row: dict[str, Any], warnings: list[str]) -> list[str]:
    images: list[str] = []
    for column in IMAGE_COLUMNS:
        if column not in row:
            continue
        for raw_path in parse_image_value(row[column]):
            source = resolve_image_path(raw_path)
            if source is None:
                warnings.append(f"Không tìm thấy ảnh: {raw_path}")
                continue
            target = unique_image_target(source.name)
            shutil.copy2(source, target)
            images.append(f"data_images/{target.name}")
    return images


def parse_image_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    if not text or text.lower() == "nan" or text == "[]":
        return []

    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple, set)):
            return [str(item).strip() for item in parsed if str(item).strip()]
        if isinstance(parsed, str):
            return [parsed]
    except (ValueError, SyntaxError):
        pass

    return [part.strip() for part in re.split(r"[;,]", text) if part.strip()]


def resolve_image_path(raw_path: str) -> Path | None:
    normalized = raw_path.replace("\\", "/").strip()
    path = Path(normalized)
    candidates = [path] if path.is_absolute() else [ROOT_DIR / normalized, IMAGE_DIR / path.name]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def unique_image_target(filename: str) -> Path:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    source_name = Path(filename).name
    stem = Path(source_name).stem or "image"
    suffix = Path(source_name).suffix
    target = IMAGE_DIR / source_name
    counter = 1
    while target.exists():
        target = IMAGE_DIR / f"{stem}_{counter}{suffix}"
        counter += 1
    return target


def translate_records(records: list[dict[str, str]]) -> None:
    for start in range(0, len(records), GEMINI_BATCH_SIZE):
        batch = records[start : start + GEMINI_BATCH_SIZE]
        translated = run_gemini(
            "Dịch các bản ghi toán tiểu học sau sang tiếng Việt. Giữ nguyên ý nghĩa toán học. "
            "Trả về JSON array cùng số phần tử, mỗi phần tử có question, answer, instruction.\n"
            f"{json.dumps([{key: record.get(key, '') for key in ['question', 'answer', 'instruction']} for record in batch], ensure_ascii=False)}"
        )
        if not isinstance(translated, list) or len(translated) != len(batch):
            raise ValueError("Gemini trả về dữ liệu dịch không đúng định dạng.")
        for record, item in zip(batch, translated):
            if not isinstance(item, dict):
                raise ValueError("Gemini trả về dữ liệu dịch không đúng định dạng.")
            for field in ("question", "answer", "instruction"):
                value = clean_text(item.get(field))
                if value:
                    record[field] = value
            if not record.get("right_choice"):
                record["right_choice"] = extract_right_choice(record.get("answer", ""))


def fill_missing_records(records: list[dict[str, str]]) -> int:
    targets = [record for record in records if needs_fill(record)]
    updated = 0
    for start in range(0, len(targets), GEMINI_BATCH_SIZE):
        batch = targets[start : start + GEMINI_BATCH_SIZE]
        filled = run_gemini(
            "Điền các trường còn thiếu cho dataset toán tiểu học bằng tiếng Việt. "
            "Không thay đổi trường đã có nội dung. Trả về JSON array cùng số phần tử, mỗi phần tử có answer, right_choice, choices, instruction. "
            "choices phải là chuỗi biểu diễn list Python, ví dụ [] nếu không có đáp án trắc nghiệm.\n"
            f"{json.dumps([{key: record.get(key, '') for key in ['question', 'answer', 'right_choice', 'choices', 'instruction']} for record in batch], ensure_ascii=False)}"
        )
        if not isinstance(filled, list) or len(filled) != len(batch):
            raise ValueError("Gemini trả về dữ liệu điền thiếu không đúng định dạng.")
        for record, item in zip(batch, filled):
            if not isinstance(item, dict):
                raise ValueError("Gemini trả về dữ liệu điền thiếu không đúng định dạng.")
            for field in ("answer", "right_choice", "choices", "instruction"):
                if record.get(field, "").strip():
                    continue
                value = clean_text(item.get(field))
                if value:
                    record[field] = value
                    updated += 1
    return updated


def needs_fill(record: dict[str, str]) -> bool:
    return bool(record.get("question", "").strip()) and any(not record.get(field, "").strip() for field in ("answer", "right_choice", "instruction"))


def run_gemini(prompt: str) -> Any:
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return json.loads(clean_gemini_json(response.text))


def clean_gemini_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()
