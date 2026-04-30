from __future__ import annotations

import ast
import csv
import math
import tempfile
import threading
from pathlib import Path
from typing import Any

from .config import CSV_COLUMNS, CSV_PATH, EDITABLE_COLUMNS
from .schemas import PaginatedRecords, RecordCreate, RecordOut, RecordUpdate

_WRITE_LOCK = threading.Lock()


def parse_list_field(value: object) -> tuple[list[str], bool]:
    if value is None:
        return [], True

    text = str(value).strip()
    if not text or text.lower() == "nan" or text == "[]":
        return [], True

    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return [], False

    if not isinstance(parsed, list):
        return [], False

    return [str(item).replace("\\", "/") for item in parsed if str(item).strip()], True


def normalize_row(row: dict[str, Any]) -> dict[str, str]:
    return {column: "" if row.get(column) is None else str(row.get(column, "")) for column in CSV_COLUMNS}


def row_to_out(row: dict[str, str]) -> RecordOut:
    parsed_choices, _ = parse_list_field(row.get("choices", ""))
    parsed_images, _ = parse_list_field(row.get("images_path", ""))
    return RecordOut(
        id=int(row["id"]),
        question=row.get("question", ""),
        answer=row.get("answer", ""),
        right_choice=row.get("right_choice", ""),
        choices=row.get("choices", ""),
        instruction=row.get("instruction", ""),
        images_path=row.get("images_path", ""),
        split_origin=row.get("split_origin", ""),
        parsed_choices=parsed_choices,
        parsed_images=parsed_images,
    )


def read_records(csv_path: Path = CSV_PATH) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [normalize_row(row) for row in reader]


def write_records(records: list[dict[str, str]], csv_path: Path = CSV_PATH) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False, dir=csv_path.parent, suffix=".tmp") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(normalize_row(record))
        temp_path = Path(file.name)

    temp_path.replace(csv_path)


def safe_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def next_id(records: list[dict[str, str]]) -> int:
    ids = [record_id for record in records if (record_id := safe_int(record.get("id"))) is not None]
    return max(ids, default=0) + 1


def find_record(records: list[dict[str, str]], record_id: int) -> dict[str, str] | None:
    for record in records:
        if safe_int(record.get("id")) == record_id:
            return record
    return None


def get_record(record_id: int) -> RecordOut | None:
    record = find_record(read_records(), record_id)
    return row_to_out(record) if record else None


def query_records(
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    split_origin: str | None = None,
    has_image: bool | None = None,
    missing_answer: bool | None = None,
    sort_by: str = "id",
    sort_dir: str = "asc",
) -> PaginatedRecords:
    records = read_records()
    search_text = (search or "").strip().lower()

    if search_text:
        searchable_columns = ["question", "answer", "right_choice", "choices", "instruction", "split_origin"]
        records = [
            record
            for record in records
            if any(search_text in record.get(column, "").lower() for column in searchable_columns)
        ]

    if split_origin:
        records = [record for record in records if record.get("split_origin", "") == split_origin]

    if has_image is not None:
        records = [record for record in records if bool(parse_list_field(record.get("images_path", ""))[0]) == has_image]

    if missing_answer is not None:
        records = [record for record in records if (not record.get("answer", "").strip()) == missing_answer]

    if sort_by not in CSV_COLUMNS:
        sort_by = "id"

    reverse = sort_dir == "desc"
    if sort_by == "id":
        records.sort(key=lambda record: safe_int(record.get("id")) or -1, reverse=reverse)
    else:
        records.sort(key=lambda record: record.get(sort_by, "").lower(), reverse=reverse)

    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    total = len(records)
    total_pages = max(math.ceil(total / page_size), 1)
    start = (page - 1) * page_size
    items = [row_to_out(record) for record in records[start : start + page_size]]
    return PaginatedRecords(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


def create_record(payload: RecordCreate) -> RecordOut:
    with _WRITE_LOCK:
        records = read_records()
        record = normalize_row(payload.model_dump())
        record["id"] = str(next_id(records))
        records.append(record)
        write_records(records)
        return row_to_out(record)


def update_record(record_id: int, payload: RecordUpdate) -> RecordOut | None:
    with _WRITE_LOCK:
        records = read_records()
        record = find_record(records, record_id)
        if record is None:
            return None

        updates = payload.model_dump(exclude_unset=True)
        for column in EDITABLE_COLUMNS:
            if column in updates and updates[column] is not None:
                record[column] = str(updates[column])

        write_records(records)
        return row_to_out(record)


def delete_record(record_id: int) -> bool:
    with _WRITE_LOCK:
        records = read_records()
        filtered = [record for record in records if safe_int(record.get("id")) != record_id]
        if len(filtered) == len(records):
            return False

        write_records(filtered)
        return True
