from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

from .config import CSV_COLUMNS, IMAGE_DIR, ROOT_DIR
from .csv_store import parse_list_field, read_records, safe_int
from .schemas import (
    BucketCount,
    DataQualityStats,
    DatasetOverview,
    MissingColumnCount,
    NumericBucketCount,
    QualityIssueRecord,
    QualityIssues,
)


def source_label(split_origin: str) -> str:
    value = split_origin.strip()
    if not value:
        return "unknown"

    parsed = urlparse(value)
    if parsed.netloc:
        return parsed.netloc

    return value[:80]


def image_exists(image_path: str) -> bool:
    normalized = image_path.replace("\\", "/").strip()
    if not normalized.startswith("data_images/"):
        return False

    relative_name = normalized.split("/", 1)[1]
    if not relative_name or "/" in relative_name or ".." in Path(relative_name).parts:
        return False

    return (IMAGE_DIR / relative_name).exists()


def get_overview() -> DatasetOverview:
    records = read_records()
    split_counts: Counter[str] = Counter()
    choice_counts: Counter[int] = Counter()
    image_counts: Counter[int] = Counter()
    total_question_length = 0
    total_answer_length = 0
    records_with_images = 0
    multiple_choice_records = 0

    for record in records:
        question = record.get("question", "")
        answer = record.get("answer", "")
        choices, _ = parse_list_field(record.get("choices", ""))
        images, _ = parse_list_field(record.get("images_path", ""))

        split_counts[source_label(record.get("split_origin", ""))] += 1
        choice_counts[len(choices)] += 1
        image_counts[len(images)] += 1
        total_question_length += len(question)
        total_answer_length += len(answer)

        if images:
            records_with_images += 1
        if choices:
            multiple_choice_records += 1

    total = len(records)
    by_split_origin = [BucketCount(label=label, count=count) for label, count in split_counts.most_common(20)]
    choice_distribution = [NumericBucketCount(value=value, count=choice_counts[value]) for value in sorted(choice_counts)]
    image_distribution = [NumericBucketCount(value=value, count=image_counts[value]) for value in sorted(image_counts)]

    return DatasetOverview(
        total_records=total,
        records_with_images=records_with_images,
        records_without_images=total - records_with_images,
        multiple_choice_records=multiple_choice_records,
        open_ended_records=total - multiple_choice_records,
        avg_question_length=round(total_question_length / total, 2) if total else 0,
        avg_answer_length=round(total_answer_length / total, 2) if total else 0,
        by_split_origin=by_split_origin,
        choice_count_distribution=choice_distribution,
        image_count_distribution=image_distribution,
    )


def collect_quality_issues() -> list[QualityIssueRecord]:
    records = read_records()
    issues: list[QualityIssueRecord] = []
    id_counts: Counter[int] = Counter()
    question_counts: Counter[str] = Counter()

    for record in records:
        record_id = safe_int(record.get("id"))
        if record_id is None:
            issues.append(QualityIssueRecord(id=None, issue_type="invalid_id", question=record.get("question", ""), detail=record.get("id", "")))
        else:
            id_counts[record_id] += 1

        question = record.get("question", "").strip()
        if question:
            question_counts[question] += 1
        else:
            issues.append(QualityIssueRecord(id=record_id, issue_type="missing_question", question="", detail="question is empty"))

        if not record.get("answer", "").strip():
            issues.append(QualityIssueRecord(id=record_id, issue_type="missing_answer", question=question, detail="answer is empty"))

        _, choices_valid = parse_list_field(record.get("choices", ""))
        if not choices_valid:
            issues.append(QualityIssueRecord(id=record_id, issue_type="invalid_choices", question=question, detail=record.get("choices", "")))

        images, images_valid = parse_list_field(record.get("images_path", ""))
        if not images_valid:
            issues.append(QualityIssueRecord(id=record_id, issue_type="invalid_images_path", question=question, detail=record.get("images_path", "")))
        for image_path in images:
            if not image_exists(image_path):
                issues.append(QualityIssueRecord(id=record_id, issue_type="missing_image_file", question=question, detail=image_path))

    duplicate_ids = {record_id for record_id, count in id_counts.items() if count > 1}
    duplicate_questions = {question for question, count in question_counts.items() if count > 1}

    for record in records:
        record_id = safe_int(record.get("id"))
        question = record.get("question", "").strip()
        if record_id in duplicate_ids:
            issues.append(QualityIssueRecord(id=record_id, issue_type="duplicate_id", question=question, detail=str(record_id)))
        if question in duplicate_questions:
            issues.append(QualityIssueRecord(id=record_id, issue_type="duplicate_question", question=question, detail=question[:160]))

    return issues


def get_quality_stats() -> DataQualityStats:
    records = read_records()
    missing_by_column = []
    for column in CSV_COLUMNS:
        missing = sum(1 for record in records if not record.get(column, "").strip())
        missing_by_column.append(MissingColumnCount(column=column, missing=missing))

    issues = collect_quality_issues()
    counts = Counter(issue.issue_type for issue in issues)
    issue_count = sum(counts.values())
    total_cells = max(len(records) * len(CSV_COLUMNS), 1)
    quality_score = max(0, 100 - (issue_count / total_cells * 100))

    return DataQualityStats(
        missing_by_column=missing_by_column,
        duplicate_ids=counts["duplicate_id"],
        duplicate_questions=counts["duplicate_question"],
        invalid_ids=counts["invalid_id"],
        invalid_choices=counts["invalid_choices"],
        invalid_images_path=counts["invalid_images_path"],
        missing_image_files=counts["missing_image_file"],
        empty_question_rows=counts["missing_question"],
        empty_answer_rows=counts["missing_answer"],
        quality_score=round(quality_score, 2),
    )


def get_quality_issues(issue_type: str | None = None, page: int = 1, page_size: int = 25) -> QualityIssues:
    issues = collect_quality_issues()
    if issue_type:
        issues = [issue for issue in issues if issue.issue_type == issue_type]

    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    total = len(issues)
    total_pages = max(math.ceil(total / page_size), 1)
    start = (page - 1) * page_size
    return QualityIssues(items=issues[start : start + page_size], page=page, page_size=page_size, total=total, total_pages=total_pages)
