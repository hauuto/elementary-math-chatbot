import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Literal
from urllib.parse import urljoin, urlparse

ProfileType = Literal["exam", "sgk"]

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CATEGORY_LINK_RE = re.compile(r"-c\d+\.html$", re.IGNORECASE)
DETAIL_LINK_RE = re.compile(r"-a\d+\.html$", re.IGNORECASE)
QUESTION_START_RE = re.compile(
    r"^\s*(?:Câu|Bài)\s*(\d+)(?:\s*\([^)]+\))?\s*[\.:)]?\s*(.*)$",
    re.IGNORECASE,
)
CHOICE_TOKEN_RE = re.compile(
    r"(?<!\w)([A-D])\s*[\.:)]\s*(.*?)(?=(?<!\w)[A-D]\s*[\.:)]\s*|$)"
)
URL_FRAGMENT_RE = re.compile(r"https?://.*?(?=https?://|$)", re.IGNORECASE)
INLINE_QUESTION_MARKER_RE = re.compile(r"(?:Câu|Bài)\s*\d+", re.IGNORECASE)
INLINE_QUESTION_SPLIT_RE = re.compile(
    r"(?=(?:Câu|Bài)\s*\d+(?:\s*\([^)]+\))?\s*[\.:)])",
    re.IGNORECASE,
)
SIMPLE_EXAM_HEADER_RE = re.compile(r"^(?:[ivxlcdm]+|phần)\s*[\.:\)]?\s*", re.IGNORECASE)
SIMPLE_ANSWER_KEY_RE = re.compile(r"^(?:đáp\s*án|hướng\s*dẫn\s*giải|lời\s*giải)\b", re.IGNORECASE)
SIMPLE_METHOD_RE = re.compile(r"^(?:phương\s*pháp|cách\s*giải)\b", re.IGNORECASE)
URL_NOISE_RE = re.compile(r"^https?://", re.IGNORECASE)
DMCA_HOST_RE = re.compile(r"(^|\.)dmca\.com$", re.IGNORECASE)
NOISE_DOMAIN_RE = re.compile(r"loigiaihay\.com", re.IGNORECASE)
EXAM_SOURCE_HINT_RE = re.compile(r"de-(?:kiem-tra|thi)|de-so", re.IGNORECASE)
SGK_SOURCE_HINT_RE = re.compile(r"(?:-sgk-|/giai-|toan-lop-|sgk)", re.IGNORECASE)
ANSWER_LIST_RE = re.compile(r"^\s*\d+\s*[\.)]\s*[A-DĐ]\b")
SECTION_PROMPT_RE = re.compile(
    r"^\s*[\(\[\{\-]*\s*(?:đề\s*bài|khoanh\s+vào\s+chữ|môn\s*:|thời\s*gian\s*làm\s*bài)",
    re.IGNORECASE,
)
EXAM_SECTION_RE = re.compile(r"^\s*(?:phần\s*\d+|[ivxlcdm]+\s*[\.:\)]\s*(?:trắc\s*nghiệm|tự\s*luận))", re.IGNORECASE)
SKIP_ANSWER_SUMMARY_RE = re.compile(r"^(?:chọn\s+[A-DĐ]|đáp\s*số)\b", re.IGNORECASE)
SCORE_PREFIX_RE = re.compile(r"^\s*\(?\s*\d+\s*điểm\s*\)?\s*[\).:\-]?\s*", re.IGNORECASE)

CSV_COLUMNS = [
    "id",
    "question",
    "answer",
    "right_choice",
    "choices",
    "instruction",
    "images_path",
    "split_origin",
]


def normalize_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def clean_question_text(value: str, profile: ProfileType) -> str:
    text = normalize_text(value)
    if not text:
        return ""

    prefix_patterns = [
        r"^\s*hoạt\s*động\s*câu\s*\d+\s*[:\.-]?\s*",
        r"^\s*luyện\s*tập\s*câu\s*\d+\s*[:\.-]?\s*",
        r"^\s*hoạt\s*động\s*\d+\s*[:\.-]?\s*",
        r"^\s*luyện\s*tập\s*\d+\s*[:\.-]?\s*",
        r"^\s*hoạt\s*động\s*[:\.-]?\s*",
        r"^\s*luyện\s*tập\s*[:\.-]?\s*",
        r"^\s*câu\s*\d+\s*[:\.-]?\s*",
        r"^\s*\(?\s*\d+\s*điểm\s*\)?\s*[\).:\-]?\s*",
    ]

    if profile == "exam":
        prefix_patterns.append(r"^\s*câu\s*[^\.!\?:]{0,40}\?\s*")

    previous = None
    while previous != text:
        previous = text
        for pattern in prefix_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    text = re.sub(r"(?:(?<=^)|(?<=[\s;:,\.-]))[a-z]\)\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.\t")
    return text


def canonical_question_key(value: str) -> str:
    text = normalize_text(value).lower()
    if not text:
        return ""

    text = SCORE_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def extract_urls_from_line(line: str) -> List[str]:
    fragments = URL_FRAGMENT_RE.findall(line)
    if not fragments and URL_NOISE_RE.match(line.strip()):
        fragments = [line.strip()]

    urls = []
    for fragment in fragments:
        cleaned = fragment.strip().strip(" \"'<>[](),;")
        if cleaned:
            urls.append(cleaned)
    return urls


def classify_link_profile(link: str, links_source: str) -> ProfileType:
    source_name = Path(links_source).name.lower()
    lowered = link.lower()

    if "sgk" in source_name:
        return "sgk"
    if EXAM_SOURCE_HINT_RE.search(lowered):
        return "exam"
    if SGK_SOURCE_HINT_RE.search(lowered):
        return "sgk"
    return "exam"


def is_answer_section_start(text: str, profile: ProfileType) -> bool:
    lowered = text.lower().strip()
    if "lời giải chi tiết" in lowered:
        return True
    if SIMPLE_METHOD_RE.match(lowered):
        return True
    if SIMPLE_ANSWER_KEY_RE.match(lowered):
        return True
    if profile == "exam" and lowered.startswith("đáp án"):
        return True
    return False


def is_noise_header_line(text: str, profile: ProfileType) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return False

    if NOISE_DOMAIN_RE.search(lowered):
        return True
    if SKIP_ANSWER_SUMMARY_RE.match(lowered):
        return True

    if profile == "sgk":
        return False

    if SECTION_PROMPT_RE.match(lowered):
        return True
    if EXAM_SECTION_RE.match(lowered):
        return True
    if SIMPLE_EXAM_HEADER_RE.match(lowered) and (
        "trắc nghiệm" in lowered or "tự luận" in lowered
    ):
        return True
    if ANSWER_LIST_RE.match(lowered):
        return True
    if lowered.startswith("đề "):
        return True
    return False


def split_inline_question_segments(text: str, profile: ProfileType) -> List[str]:
    if not text:
        return []

    if profile != "exam":
        return [text]

    marker_matches = INLINE_QUESTION_MARKER_RE.findall(text)
    if not marker_matches:
        return [text]

    if len(marker_matches) == 1 and QUESTION_START_RE.match(text):
        return [text]

    segments = [
        normalize_text(segment)
        for segment in INLINE_QUESTION_SPLIT_RE.split(text)
        if normalize_text(segment)
    ]
    return segments if segments else [text]


def should_skip_row(question: str, choices: List[str], image_urls: List[str]) -> bool:
    return not question and not choices and not image_urls


def finalize_block(block: Dict) -> Dict:
    return {
        "question_parts": unique_preserve_order([q for q in block.get("question_parts", []) if q]),
        "choices": unique_preserve_order(block.get("choices", [])),
        "image_urls": unique_preserve_order(block.get("image_urls", [])),
        "answer_parts": unique_preserve_order([a for a in block.get("answer_parts", []) if a]),
    }


def start_new_block(text: str, images: List[str]) -> Dict:
    return {
        "question_parts": [text] if text else [],
        "choices": [],
        "image_urls": list(images),
        "answer_parts": [],
    }


def append_record_if_valid(records: List[Dict], block: Dict | None) -> None:
    if block is None:
        return
    final_block = finalize_block(block)
    if final_block["question_parts"] or final_block["image_urls"]:
        records.append(final_block)


def should_skip_link(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if DMCA_HOST_RE.search(host):
        return True

    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else url
    if CATEGORY_LINK_RE.search(base_url):
        return True
    if not DETAIL_LINK_RE.search(base_url):
        return True
    return False


def normalize_link(url: str) -> str:
    parsed = urlparse(url)
    if not (parsed.scheme and parsed.netloc):
        return url
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def build_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
    )
    return session


def load_links(links_file: Path) -> List[str]:
    lines = [line.strip() for line in links_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    extracted_urls = []
    for line in lines:
        extracted_urls.extend(extract_urls_from_line(line))

    dedup = unique_preserve_order(extracted_urls)

    filtered = []
    for link in dedup:
        normalized = normalize_link(link)
        if should_skip_link(normalized):
            continue
        filtered.append(normalized)

    return filtered


def parse_choices_from_text(text: str) -> List[str]:
    matches = CHOICE_TOKEN_RE.findall(text)
    if not matches:
        return []

    starts_with_choice = bool(re.match(r"^\s*[A-D]\s*[\.:)]", text))
    if len(matches) < 2 and not starts_with_choice:
        return []

    parsed = []
    for label, content in matches:
        label = label.upper()
        content = normalize_text(content)
        parsed.append(f"{label}. {content}" if content else f"{label}.")
    return unique_preserve_order(parsed)


def update_question_mode(text: str, current_mode: str) -> str:
    lowered = text.lower()
    if "trắc nghiệm" in lowered:
        return "objective"
    if "tự luận" in lowered:
        return "essay"
    return current_mode


def extract_question_blocks_from_single_container(container, page_url: str, profile: ProfileType) -> List[Dict]:
    paragraphs = container.find_all("p")
    records = []
    current = None
    mode = "objective"
    in_answer_section = False

    for p in paragraphs:
        raw_text = normalize_text(p.get_text(" ", strip=True))
        images = [urljoin(page_url, img["src"]) for img in p.find_all("img", src=True)]
        segments = split_inline_question_segments(raw_text, profile) if raw_text else [""]

        for idx, text in enumerate(segments):
            segment_images = images if idx == 0 else []

            if text:
                mode = update_question_mode(text, mode)

            if not text and not segment_images:
                continue

            if text and is_noise_header_line(text, profile):
                if segment_images and current is not None:
                    current["image_urls"].extend(segment_images)
                continue

            if text and is_answer_section_start(text, profile):
                in_answer_section = True
                continue

            start_match = QUESTION_START_RE.match(text)
            if start_match:
                in_answer_section = False
                append_record_if_valid(records, current)
                current = start_new_block(text, segment_images)
                continue

            if current is None:
                continue

            if in_answer_section:
                if text:
                    current["answer_parts"].append(text)
                if segment_images:
                    current["image_urls"].extend(segment_images)
                continue

            choices = parse_choices_from_text(text) if (text and mode == "objective") else []
            if choices:
                current["choices"].extend(choices)
            elif text:
                current["question_parts"].append(text)

            if segment_images:
                current["image_urls"].extend(segment_images)

    append_record_if_valid(records, current)
    return records


def extract_question_blocks_from_multi_subquestions(
    soup: BeautifulSoup,
    page_url: str,
    profile: ProfileType,
) -> List[Dict]:
    blocks = []
    containers = soup.select('div.box-question.content-box-unit[id^="sub-question-"]')

    for container in containers:
        container_records = []
        current = None
        mode = "objective"
        in_answer_section = False

        paragraphs = container.find_all("p")
        for p in paragraphs:
            raw_text = normalize_text(p.get_text(" ", strip=True))
            images = [urljoin(page_url, img["src"]) for img in p.find_all("img", src=True)]
            segments = split_inline_question_segments(raw_text, profile) if raw_text else [""]

            for idx, text in enumerate(segments):
                segment_images = images if idx == 0 else []

                if text:
                    mode = update_question_mode(text, mode)

                if not text and not segment_images:
                    continue

                if text and is_noise_header_line(text, profile):
                    if segment_images and current is not None:
                        current["image_urls"].extend(segment_images)
                    continue

                if text and is_answer_section_start(text, profile):
                    in_answer_section = True
                    continue

                start_match = QUESTION_START_RE.match(text)
                if start_match:
                    in_answer_section = False
                    append_record_if_valid(container_records, current)
                    current = start_new_block(text, segment_images)
                    continue

                if current is None and in_answer_section:
                    continue

                if current is None:
                    current = start_new_block(text, segment_images)

                if in_answer_section:
                    if text:
                        current["answer_parts"].append(text)
                    if segment_images:
                        current["image_urls"].extend(segment_images)
                    continue

                maybe_choices = parse_choices_from_text(text) if (text and mode == "objective") else []
                if maybe_choices:
                    current["choices"].extend(maybe_choices)
                elif text:
                    current["question_parts"].append(text)

                if segment_images:
                    current["image_urls"].extend(segment_images)

        append_record_if_valid(container_records, current)
        blocks.extend(container_records)

    return blocks


def extract_question_blocks(html: str, page_url: str, profile: ProfileType) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    sub_question_containers = soup.select('div.box-question.content-box-unit[id^="sub-question-"]')
    if len(sub_question_containers) > 1:
        multi_blocks = extract_question_blocks_from_multi_subquestions(soup, page_url, profile)
        if multi_blocks:
            return multi_blocks

    container = (
        soup.select_one("div#sub-question-1")
        or soup.select_one("div.box-question.content-box-unit")
        or soup.select_one("#box-content")
    )
    if container is None:
        return []

    return extract_question_blocks_from_single_container(container, page_url, profile)


def download_images(
    session: requests.Session,
    image_urls: List[str],
    images_dir: Path,
    record_id: str,
    relative_root: Path,
) -> List[str]:
    local_paths = []
    for idx, image_url in enumerate(unique_preserve_order([u for u in image_urls if u]), start=1):
        try:
            response = session.get(image_url, timeout=30)
            response.raise_for_status()

            ext = Path(urlparse(image_url).path).suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
                ext = ".jpg"

            filename = f"{record_id}_{idx}{ext}"
            image_path = images_dir / filename
            image_path.write_bytes(response.content)

            try:
                relative_path = image_path.resolve().relative_to(relative_root.resolve()).as_posix()
            except ValueError:
                relative_path = os.path.relpath(image_path.resolve(), relative_root.resolve()).replace("\\", "/")

            local_paths.append(relative_path)
        except Exception:
            continue
    return local_paths


def crawl(
    links: List[str],
    output_csv: Path,
    images_dir: Path,
    errors_file: Path,
    max_links: int | None,
    links_source: str,
) -> None:
    session = build_session()
    images_dir.mkdir(parents=True, exist_ok=True)

    if max_links is not None:
        links = links[:max_links]

    file_exists = output_csv.exists() and output_csv.stat().st_size > 0
    next_id = 1
    errors = []
    relative_root = Path(__file__).resolve().parent

    with output_csv.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()

        for i, link in enumerate(links, start=1):
            print(f"[{i}/{len(links)}] Crawling: {link}")
            try:
                resp = session.get(link, timeout=40)
                resp.raise_for_status()

                profile = classify_link_profile(link, links_source)
                blocks = extract_question_blocks(resp.text, link, profile)
                if not blocks:
                    errors.append({"url": link, "error": "No question blocks found"})
                    continue

                raw_rows = []
                skipped_blocks = 0
                for block in blocks:
                    raw_question = normalize_text(" ".join(block["question_parts"])) if block["question_parts"] else ""
                    question = clean_question_text(raw_question, profile)
                    answer_text = normalize_text(" ".join(block.get("answer_parts", []))) if block.get("answer_parts") else ""

                    if profile == "exam" and SECTION_PROMPT_RE.match(question):
                        skipped_blocks += 1
                        continue

                    if should_skip_row(question, block["choices"], block["image_urls"]):
                        skipped_blocks += 1
                        continue

                    raw_rows.append(
                        {
                            "question": question,
                            "answer": answer_text,
                            "choices": list(block["choices"]),
                            "image_urls": list(block["image_urls"]),
                        }
                    )

                if profile == "exam" and raw_rows:
                    dedup_rows = {}
                    dedup_order = []
                    for idx, row in enumerate(raw_rows):
                        dedup_key = canonical_question_key(row["question"])
                        if not dedup_key:
                            dedup_key = f"__questionless__::{idx}"

                        if dedup_key not in dedup_rows:
                            dedup_rows[dedup_key] = row
                            dedup_order.append(dedup_key)
                            continue

                        existing = dedup_rows[dedup_key]
                        if len(row["answer"]) > len(existing["answer"]):
                            existing["answer"] = row["answer"]
                        if len(row["question"]) > len(existing["question"]):
                            existing["question"] = row["question"]
                        existing["choices"] = unique_preserve_order(existing["choices"] + row["choices"])
                        existing["image_urls"] = unique_preserve_order(existing["image_urls"] + row["image_urls"])

                    raw_rows = [dedup_rows[key] for key in dedup_order]

                rows_for_this_link = []
                for row in raw_rows:
                    record_id = str(next_id)
                    next_id += 1
                    images_path = download_images(
                        session=session,
                        image_urls=row["image_urls"],
                        images_dir=images_dir,
                        record_id=record_id,
                        relative_root=relative_root,
                    )

                    rows_for_this_link.append(
                        {
                            "id": record_id,
                            "question": row["question"],
                            "answer": row["answer"],
                            "right_choice": "",
                            "choices": json.dumps(row["choices"], ensure_ascii=False),
                            "instruction": "",
                            "images_path": json.dumps(images_path, ensure_ascii=False),
                            "split_origin": link,
                        }
                    )

                if rows_for_this_link:
                    writer.writerows(rows_for_this_link)
                    f.flush()
                    print(f"   Collected {len(rows_for_this_link)} rows")
                if skipped_blocks:
                    errors.append({"url": link, "error": f"Skipped {skipped_blocks} empty/noisy blocks"})

            except Exception as exc:
                print(f"   Error at {link}: {exc}")
                errors.append({"url": link, "error": str(exc)})
                errors_file.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        errors_file.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone! Data saved at {output_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Math extraction pipeline")
    parser.add_argument("--links", default="links.txt", help="Input links file")
    parser.add_argument("--output", default="crawled_math_with_images.csv", help="Output CSV")
    parser.add_argument("--images-dir", default="downloaded_images", help="Directory for images")
    parser.add_argument("--errors", default="crawl_errors.json", help="Error log JSON")
    parser.add_argument("--max-links", type=int, default=None, help="Limit links for testing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    links = load_links(Path(args.links))
    print(f"Loaded {len(links)} unique detail links after filtering")

    crawl(
        links=links,
        output_csv=Path(args.output),
        images_dir=Path(args.images_dir),
        errors_file=Path(args.errors),
        max_links=args.max_links,
        links_source=args.links,
    )


if __name__ == "__main__":
    main()
