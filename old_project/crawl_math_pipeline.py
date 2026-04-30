import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin, urlparse

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


def clean_question_text(value: str) -> str:
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
        r"^\s*câu\s*[^\.!\?:]{0,40}\?\s*",
    ]

    previous = None
    while previous != text:
        previous = text
        for pattern in prefix_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    text = re.sub(r"(?:(?<=^)|(?<=[\s;:,\.-]))[a-z]\)\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.\t")
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
    dedup = unique_preserve_order(lines)

    filtered = []
    for link in dedup:
        if CATEGORY_LINK_RE.search(link):
            continue
        if DETAIL_LINK_RE.search(link):
            filtered.append(link)
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


def extract_question_blocks_from_single_container(container, page_url: str) -> List[Dict]:
    paragraphs = container.find_all("p")
    records = []
    current = None
    mode = "objective"
    in_answer_section = False

    for p in paragraphs:
        text = normalize_text(p.get_text(" ", strip=True))
        images = [urljoin(page_url, img["src"]) for img in p.find_all("img", src=True)]

        if text:
            mode = update_question_mode(text, mode)

        if not text and not images:
            continue

        lowered = text.lower()
        if "lời giải chi tiết" in lowered:
            in_answer_section = True
            continue
        if "phương pháp giải" in lowered:
            continue

        start_match = QUESTION_START_RE.match(text)
        if start_match:
            in_answer_section = False
            if current is not None:
                current["choices"] = unique_preserve_order(current["choices"])
                current["image_urls"] = unique_preserve_order(current["image_urls"])
                records.append(current)
            current = {
                "question_parts": [text] if text else [],
                "choices": [],
                "image_urls": list(images),
                "answer_parts": [],
            }
            continue

        if current is None:
            continue

        if in_answer_section:
            if text:
                current["answer_parts"].append(text)
            continue

        choices = parse_choices_from_text(text) if mode == "objective" else []
        if choices:
            current["choices"].extend(choices)
        else:
            if text:
                current["question_parts"].append(text)

        if images:
            current["image_urls"].extend(images)

    if current is not None:
        current["choices"] = unique_preserve_order(current["choices"])
        current["image_urls"] = unique_preserve_order(current["image_urls"])
        records.append(current)

    return records


def extract_question_blocks_from_multi_subquestions(soup: BeautifulSoup, page_url: str) -> List[Dict]:
    blocks = []
    containers = soup.select('div.box-question.content-box-unit[id^="sub-question-"]')

    for container in containers:
        question_parts = []
        choices = []
        image_urls = []
        answer_parts = []
        in_answer_section = False

        paragraphs = container.find_all("p")
        for p in paragraphs:
            text = normalize_text(p.get_text(" ", strip=True))
            images = [urljoin(page_url, img["src"]) for img in p.find_all("img", src=True)]

            if p.get("id", "").startswith("question-title-idx-"):
                if text:
                    question_parts.append(text)
                image_urls.extend(images)
                continue

            lowered = text.lower()
            if "lời giải chi tiết" in lowered:
                in_answer_section = True
                continue
            if "phương pháp giải" in lowered:
                continue

            if in_answer_section:
                if text:
                    answer_parts.append(text)
                continue

            if text:
                question_parts.append(text)
            image_urls.extend(images)

            maybe_choices = parse_choices_from_text(text)
            if maybe_choices:
                choices.extend(maybe_choices)

        if question_parts or image_urls:
            blocks.append(
                {
                    "question_parts": unique_preserve_order([q for q in question_parts if q]),
                    "choices": unique_preserve_order(choices),
                    "image_urls": unique_preserve_order(image_urls),
                    "answer_parts": unique_preserve_order([a for a in answer_parts if a]),
                }
            )

    return blocks


def extract_question_blocks(html: str, page_url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    sub_question_containers = soup.select('div.box-question.content-box-unit[id^="sub-question-"]')
    if len(sub_question_containers) > 1:
        multi_blocks = extract_question_blocks_from_multi_subquestions(soup, page_url)
        if multi_blocks:
            return multi_blocks

    container = (
        soup.select_one("div#sub-question-1")
        or soup.select_one("div.box-question.content-box-unit")
        or soup.select_one("#box-content")
    )
    if container is None:
        return []

    return extract_question_blocks_from_single_container(container, page_url)


def download_images(session: requests.Session, image_urls: List[str], images_dir: Path, record_id: str) -> List[str]:
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
            local_paths.append(image_path.as_posix())
        except Exception:
            continue
    return local_paths


def crawl(links: List[str], output_csv: Path, images_dir: Path, errors_file: Path, max_links: int | None) -> None:
    session = build_session()
    images_dir.mkdir(parents=True, exist_ok=True)

    if max_links is not None:
        links = links[:max_links]

    # Kiểm tra file tồn tại để viết Header
    file_exists = output_csv.exists() and output_csv.stat().st_size > 0
    
    # Logic lấy next_id: Nếu file đã có data, bạn nên tính toán lại next_id để tránh trùng
    next_id = 1 
    errors = []

    # Mở file một lần duy nhất ở chế độ append
    with output_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()

        for i, link in enumerate(links, start=1):
            print(f"[{i}/{len(links)}] Crawling: {link}")
            try:
                resp = session.get(link, timeout=40)
                resp.raise_for_status()

                blocks = extract_question_blocks(resp.text, link)
                if not blocks:
                    errors.append({"url": link, "error": "No question blocks found"})
                    continue

                # Chuẩn bị list data cho link hiện tại
                rows_for_this_link = []
                for block in blocks:
                    record_id = str(next_id)
                    next_id += 1
                    
                    raw_question = normalize_text(" ".join(block["question_parts"])) if block["question_parts"] else ""
                    question = clean_question_text(raw_question)
                    answer_text = normalize_text(" ".join(block.get("answer_parts", []))) if block.get("answer_parts") else ""
                    
                    # Tải ảnh
                    images_path = download_images(session, block["image_urls"], images_dir, record_id)

                    rows_for_this_link.append({
                        "id": record_id,
                        "question": question,
                        "answer": answer_text,
                        "right_choice": "",
                        "choices": json.dumps(block["choices"], ensure_ascii=False),
                        "instruction": "",
                        "images_path": json.dumps(images_path, ensure_ascii=False),
                        "split_origin": link,
                    })

                # Ghi toàn bộ List của link này vào File
                if rows_for_this_link:
                    writer.writerows(rows_for_this_link)
                    f.flush() # Đẩy dữ liệu từ RAM xuống đĩa ngay lập tức
                    print(f"   ✅ Đã thu nhận {len(rows_for_this_link)} data")

            except Exception as exc:
                print(f"   ⚠️ Lỗi tại {link}: {exc}")
                errors.append({"url": link, "error": str(exc)})
                # Lưu log lỗi định kỳ
                errors_file.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nHoàn thành! Dữ liệu đã được bảo lưu an toàn tại {output_csv}")


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
    )


if __name__ == "__main__":
    main()
