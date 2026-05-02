#!/usr/bin/env python3
"""
Data statistics and quality report for data_warehouse.csv
"""
from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[1]

LOGGER = logging.getLogger("data_stats")


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split())


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
    except Exception:
        return [item.strip() for item in re.split(r"\s*,\s*", value) if item.strip()]
    if isinstance(decoded, list):
        return [str(item) for item in decoded if str(item).strip()]
    return []


def cell_is_missing(row: dict[str, str], field_name: str) -> bool:
    value = row.get(field_name)
    if field_name in {"choices", "images_path"}:
        return len(parse_list_cell(value)) == 0
    return not normalize_text(value)


def main() -> None:
    setup_logging()
    
    csv_path = PROJECT_ROOT / "data_warehouse.csv"
    
    if not csv_path.exists():
        LOGGER.error("CSV file not found: %s", csv_path)
        return
    
    # Parse CSV
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    total = len(rows)
    LOGGER.info("=" * 70)
    LOGGER.info("DATA WAREHOUSE STATISTICS")
    LOGGER.info("=" * 70)
    LOGGER.info("Total rows: %d", total)
    LOGGER.info("")
    
    # Count by field presence
    missing_answer = 0
    missing_right_choice = 0
    missing_choices = 0
    missing_instruction = 0
    missing_question = 0
    has_image = 0
    
    origin_counts = defaultdict(int)
    
    for row in rows:
        if cell_is_missing(row, "answer"):
            missing_answer += 1
        if cell_is_missing(row, "right_choice"):
            missing_right_choice += 1
        if cell_is_missing(row, "choices"):
            missing_choices += 1
        if cell_is_missing(row, "instruction"):
            missing_instruction += 1
        if cell_is_missing(row, "question"):
            missing_question += 1
        if parse_list_cell(row.get("images_path")):
            has_image += 1
        
        origin = row.get("split_origin", "")
        if origin:
            origin_counts[origin] += 1
        else:
            origin_counts["(no origin)"] += 1
    
    LOGGER.info("FIELD PRESENCE:")
    LOGGER.info("  With answer:           %6d (%5.1f%%)", total - missing_answer, 100 * (total - missing_answer) / total)
    LOGGER.info("  Missing answer:        %6d (%5.1f%%)", missing_answer, 100 * missing_answer / total)
    LOGGER.info("  With right_choice:     %6d (%5.1f%%)", total - missing_right_choice, 100 * (total - missing_right_choice) / total)
    LOGGER.info("  Missing right_choice:  %6d (%5.1f%%)", missing_right_choice, 100 * missing_right_choice / total)
    LOGGER.info("  With choices:          %6d (%5.1f%%)", total - missing_choices, 100 * (total - missing_choices) / total)
    LOGGER.info("  Missing choices:       %6d (%5.1f%%)", missing_choices, 100 * missing_choices / total)
    LOGGER.info("  With instruction:      %6d (%5.1f%%)", total - missing_instruction, 100 * (total - missing_instruction) / total)
    LOGGER.info("  Missing instruction:   %6d (%5.1f%%)", missing_instruction, 100 * missing_instruction / total)
    LOGGER.info("  With question:         %6d (%5.1f%%)", total - missing_question, 100 * (total - missing_question) / total)
    LOGGER.info("  Missing question:      %6d (%5.1f%%)", missing_question, 100 * missing_question / total)
    LOGGER.info("  With image:            %6d (%5.1f%%)", has_image, 100 * has_image / total)
    LOGGER.info("")
    
    # Count by origin/source
    LOGGER.info("DATA ORIGIN:")
    for origin in sorted(origin_counts.keys()):
        count = origin_counts[origin]
        if origin.startswith("augmentation"):
            LOGGER.info("  %s: %6d", origin, count)
        else:
            # truncate long URLs
            display_origin = origin if len(origin) < 60 else origin[:57] + "..."
            LOGGER.info("  %s: %6d", display_origin, count)
    LOGGER.info("")
    
    # Combined missing counts
    LOGGER.info("ROWS WITH MULTIPLE MISSING FIELDS:")
    both_missing = 0
    missing_multiple = 0
    for row in rows:
        missing_count = sum([
            cell_is_missing(row, "answer"),
            cell_is_missing(row, "right_choice"),
            cell_is_missing(row, "choices"),
            cell_is_missing(row, "instruction"),
            cell_is_missing(row, "question"),
        ])
        if missing_count >= 2:
            missing_multiple += 1
    
    LOGGER.info("  Rows with 2+ missing fields: %d", missing_multiple)
    LOGGER.info("")
    
    # Recommendations
    LOGGER.info("RECOMMENDATIONS:")
    if missing_answer > 0:
        LOGGER.info("  - Run --fill-missing to generate answers for %d rows", missing_answer)
    if missing_question > 0:
        LOGGER.info("  - %d rows have missing questions; these may need manual review", missing_question)
    if missing_instruction > 0:
        LOGGER.info("  - %d rows have missing instructions", missing_instruction)
    
    LOGGER.info("=" * 70)


if __name__ == "__main__":
    main()
