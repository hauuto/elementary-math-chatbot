from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = DASHBOARD_DIR.parent
CSV_PATH = ROOT_DIR / "data_warehouse.csv"
IMAGE_DIR = ROOT_DIR / "data_images"

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
