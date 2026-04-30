import os
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = DASHBOARD_DIR.parent
CSV_PATH = ROOT_DIR / "data_warehouse.csv"
IMAGE_DIR = ROOT_DIR / "data_images"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_BATCH_SIZE = int(os.getenv("GEMINI_BATCH_SIZE", "10"))

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

EDITABLE_COLUMNS = [column for column in CSV_COLUMNS if column != "id"]
