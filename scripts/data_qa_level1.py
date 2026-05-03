# poetry add pandas
import os
import ast
import logging
import pandas as pd
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = [
    "id", "question", "answer", "right_choice",
    "choices", "instruction", "images_path", "split_origin"
]

def check_schema(df: pd.DataFrame) -> bool:
    """Check if the DataFrame has exactly the expected columns."""
    logger.info("Kiểm tra schema các cột...")
    columns = df.columns.tolist()
    missing = [col for col in EXPECTED_COLUMNS if col not in columns]
    extra = [col for col in columns if col not in EXPECTED_COLUMNS]

    if missing:
        logger.error(f"Thiếu các cột: {missing}")
    if extra:
        logger.error(f"Thừa các cột: {extra}")

    if not missing and not extra:
        logger.info("Schema cột hợp lệ.")

    return len(missing) == 0 and len(extra) == 0

def check_data_rules(df: pd.DataFrame, project_root: str):
    """Validate data logic based on schema rules."""
    logger.info("Kiểm tra logic rules của dữ liệu...")
    errors = []

    for index, row in df.iterrows():
        row_id = row.get("id", f"Row-{index}")

        # 1. Validate choices & detect if question is 'tự luận' (essay/open-ended)
        choices_str = str(row.get("choices", "")).strip()
        is_tu_luan = False

        if pd.isna(row.get("choices")) or choices_str in ["", "[]", '[""]', "['']", "nan"]:
            is_tu_luan = True
        else:
            try:
                choices_list = ast.literal_eval(choices_str)
                if not isinstance(choices_list, list):
                    errors.append(f"[{row_id}] 'choices' phải là dạng list, nhận được: {choices_str}")
                elif len(choices_list) == 0 or (len(choices_list) == 1 and choices_list[0] == ""):
                    is_tu_luan = True
            except Exception:
                errors.append(f"[{row_id}] 'choices' không đúng định dạng list hợp lệ của Python: {choices_str}")

        # 2. Validate right_choice for 'tự luận' (có thể là số hoặc chữ đối với câu hỏi logic)
        if is_tu_luan:
            right_choice = str(row.get("right_choice", "")).strip()
            if right_choice == "nan" or right_choice == "":
                errors.append(f"[{row_id}] 'right_choice' bị trống (tự luận).")
            # Đã bỏ qua ràng buộc bắt buộc phải là số (regex r"[-0-9.,/ ]+") vì câu hỏi logic có thể chứa chữ.

        # 3. Validate images_path
        img_path = row.get("images_path")
        if pd.notna(img_path) and str(img_path).strip() != "" and str(img_path) != "nan":
            img_path_str = str(img_path).strip()
            if img_path_str in ["[]", "['']", '[""]']:
                pass  # Không có ảnh, hợp lệ
            else:
                try:
                    img_list = ast.literal_eval(img_path_str)
                    if not isinstance(img_list, list):
                        errors.append(f"[{row_id}] 'images_path' phải là định dạng list, nhận được: {img_path_str}")
                    else:
                        for p in img_list:
                            p_str = str(p).strip()
                            if not p_str.startswith("data_images/"):
                                errors.append(f"[{row_id}] 'images_path' tử phải là đường dẫn tương đối (bắt đầu bằng 'data_images/'), nhận được: {p_str}")
                            else:
                                full_path = os.path.join(project_root, p_str)
                                if not os.path.exists(full_path):
                                    errors.append(f"[{row_id}] File ảnh không tồn tại: {full_path}")
                except Exception:
                    # Trong trường hợp string thuần (không phải format list)
                    if not img_path_str.startswith("data_images/"):
                        errors.append(f"[{row_id}] 'images_path' phải là đường dẫn tương đối (bắt đầu bằng 'data_images/'), nhận được: {img_path_str}")
                    else:
                        full_path = os.path.join(project_root, img_path_str)
                        if not os.path.exists(full_path):
                            errors.append(f"[{row_id}] File ảnh không tồn tại: {full_path}")

    # Output results
    if errors:
        logger.error(f"Phát hiện {len(errors)} lỗi dữ liệu:")

        # Lưu toàn bộ lỗi ra file log để dễ kiểm tra
        error_log_path = os.path.join(project_root, "qa_errors.log")
        with open(error_log_path, "w", encoding="utf-8") as f:
            for err in errors:
                f.write(err + "\n")
        logger.info(f"Đã lưu toàn bộ chi tiết {len(errors)} lỗi ra file: {error_log_path}")

        for err in errors[:50]:  # Print up to 50 errors
            logger.error(err)
        if len(errors) > 50:
            logger.error(f"... và {len(errors) - 50} lỗi khác (vui lòng xem đầy đủ trong file {error_log_path}).")
    else:
        logger.info("Dữ liệu hợp lệ, không phát hiện lỗi nào theo luật đề ra!")

def run_qa():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    csv_path = os.path.join(project_root, "data_warehouse.csv")

    if not os.path.exists(csv_path):
        logger.error(f"Không tìm thấy file {csv_path}")
        return

    logger.info(f"Đọc dữ liệu từ {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        logger.error(f"Lỗi khi đọc file CSV: {str(e)}")
        return

    is_schema_valid = check_schema(df)
    if is_schema_valid:
        check_data_rules(df, project_root)
    else:
        logger.error("Dừng kiểm tra dữ liệu do schema bị lỗi.")

if __name__ == "__main__":
    run_qa()
