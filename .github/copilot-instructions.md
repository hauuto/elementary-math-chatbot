# GitHub Copilot Instructions — Vietnamese Elementary Math Chatbot

## Project Overview

This is an NLP academic project: a Vietnamese chatbot that solves elementary school math problems (toán tiểu học). The goal is to demonstrate a progression of deep learning approaches from baseline to modern architectures.

- **Team:** 2 people
- **Timeline:** 4 days
- **Academic goal:** Compare 4 model architectures — RNN baseline → Transformer → Pretrained LLM (multimodal) → Pretrained LLM (math-specialized)
- **Dependency management:** Poetry (`pyproject.toml` is the single source of truth — never use `pip install` directly in code or scripts; always add deps via `poetry add`)

---

## Repository Structure

```
project/
├── pyproject.toml              # Poetry dependency manifest (single source of truth)
├── poetry.lock
├── data_warehouse.csv          # Main data source containing all records (CSV format)
├── data_images/                # All images for the problems (do not modify manually)
├── models/
│   ├── m1_lstm/
│   │   ├── train.ipynb         # Kaggle training notebook
│   │   ├── inference.py
│   │   ├── vocab.py            # Vocabulary builder for M1/M2
│   │   └── README.md
│   ├── m2_transformer/
│   │   ├── train.ipynb         # Kaggle training notebook
│   │   ├── inference.py
│   │   ├── vocab.py
│   │   └── README.md
│   ├── m3_gemma/
│   │   ├── train.ipynb         # Kaggle training notebook
│   │   ├── inference.py
│   │   └── README.md
│   └── m4_qwen/
│       ├── train.ipynb         # Kaggle training notebook
│       ├── inference.py
│       └── README.md
├── pipeline/
│   ├── image_router.py         # OCR + Gemini Vision routing logic
│   ├── ocr.py                  # PaddleOCR wrapper
│   └── gemini_vision.py        # Gemini Vision API wrapper
├── backend/
│   ├── main.py                 # FastAPI app
│   ├── inference.py            # Unified inference for all 4 models
│   └── schemas.py              # Pydantic request/response schemas
├── frontend/
│   └── app.py                  # Gradio chat interface
├── evaluation/
│   ├── metrics.py              # Answer Accuracy, BLEU, ROUGE
│   ├── llm_judge.py            # Gemini-as-judge for CoT quality
│   ├── run_eval.py             # Evaluation runner for all models
│   └── results/                # Saved evaluation JSON outputs per model
├── scripts/
│   ├── generate_synthetic.py   # Synthetic data generation via Gemini API
│   ├── data_qa_level1.py       # Automated QA script (Level 1)
│   └── scraper.py              # Web scraper for additional data
├── config.py                   # All configurable constants (never hardcode values)
└── notebooks/
    └── analysis.ipynb          # Data distribution analysis
```

---

## Dependency Management (Poetry)

**Critical rules — Copilot must follow these in every generated file:**

- Never write `pip install <package>` in scripts or READMEs. Always use `poetry add <package>` or `poetry add --group dev <package>`.
- Never import a package that is not declared in `pyproject.toml`. If a new package is needed, note it as a `# poetry add <package>` comment at the top of the file where it is first used.
- Use `poetry run python <script>` for all execution examples in READMEs and scripts.
- The virtual environment is managed entirely by Poetry — never reference `.venv` paths directly.

**Core dependency groups in `pyproject.toml`:**

```toml
[tool.poetry.dependencies]
python = "^3.10"
torch = "*"
transformers = "*"
peft = "*"
bitsandbytes = "*"
paddleocr = "*"
google-generativeai = "*"
fastapi = "*"
uvicorn = "*"
gradio = "*"
evaluate = "*"
nltk = "*"
rouge-score = "*"
pillow = "*"

[tool.poetry.group.dev.dependencies]
jupyter = "*"
ipykernel = "*"
```

---

## Data Schema

Tiêu chuẩn dữ liệu được lưu trên cùng 1 file CSV (`data_warehouse.csv`), chứa các cột định dạng như sau:

| Column | Type | Note |
| :--- | :--- | :--- |
| **id** | String | Định danh duy nhất (tuần tự học ngẫu nhiên). |
| **question** | Text | Chứa nội dung bài tập. |
| **answer** | Text | Lời giải CoT từng bước. |
| **right_choice**| String | Đáp án thuần túy (số nếu tự luận, A/B/C/D nếu trắc nghiệm). |
| **choices** | String | Định dạng list chứa các lựa chọn. VD: `["A. 1", "B. 2"]`. Tự luận để rỗng hoặc `[""]`. |
| **instruction** | Text | Prompt instruction. |
| **images_path** | String | Đường dẫn tương đối từ project root (VD: `data_images/image.png`) hoặc rỗng. |
| **split_origin** | String | Nguồn thu thập dữ liệu (có thể là URL, vimathqa, synthetic, v.v.). |

**Schema rules (strictly enforced by QA scripts):**
- Cấu trúc chung theo format trên. Không được thêm/bớt các cột ngoài ý muốn. Dữ liệu đã được clean nên không có cột split.
- `right_choice` for tự luận = the numeric answer only — no units, no Vietnamese text (e.g., `"72"` not `"72 cái kẹp"`)
- `choices` for tự luận = `[""]` hoặc rỗng
- `images_path` must be a relative path from project root, e.g., `data_images/[number1]_[number2].png`

---

## Model Architecture Overview

| ID | Name | Type | Framework | Notes |
|----|------|------|-----------|-------|
| M1 | LSTM Language Model | From scratch | PyTorch | Text generation, no attention |
| M2 | Transformer Decoder | From scratch | PyTorch | Standard decoder-only architecture |
| M3 | Gemma 4 E2B IT + QLoRA | Fine-tuned | HuggingFace + PEFT | Text-only (images processed via OCR/Vision) |
| M4 | Qwen2.5-Math-1.5B + QLoRA | Fine-tuned | HuggingFace + PEFT | Math-specialized, text-only |

**Research question for M3 vs M4:** Trade-off between general instruction capability (M3) and math domain specialization (M4).

### Common Inference Interface

All 4 models must expose this interface in their respective `inference.py`:

```python
def generate(prompt: str) -> str:
    """
    Generate a solution for the given math problem.

    Args:
        prompt: The math problem text (Vietnamese) including any text extracted from images.
    Returns:
        The generated solution string (Vietnamese CoT).
    """
    ...
```

**Additional rules per model type:**
- M1 and M2: pure PyTorch only, no HuggingFace Trainer
- M1 and M2: must load vocab from their respective `vocab.json` at inference time
- M3 and M4: always use `peft` with `LoraConfig`, `bitsandbytes` for 4-bit quantization, and `trl.SFTTrainer`

---

## Compute & Hardware Constraints

- **Training platform:** Kaggle (free T4 × 2 or P100 GPUs)
- **T4 VRAM:** 16 GB per GPU — strictly enforce the following for M3 and M4 training:
  - `load_in_4bit=True` via `BitsAndBytesConfig`
  - `per_device_train_batch_size=1`
  - `gradient_accumulation_steps=4`
  - `gradient_checkpointing=True`
  - `optim="paged_adamw_8bit"`
- **OCR:** PaddleOCR runs on CPU — no GPU dependency
- **Vision preprocessing:** Gemini Vision API (key via env var `GEMINI_API_KEY`)
- **Synthetic data generation:** Gemini API (same key)
- **Frontend:** Gradio (`gr.ChatInterface` with file upload support)

**Python version:** 3.10+

---

## Configuration (`config.py`)

All configurable values must live in `config.py` and be read from environment variables with sensible defaults. Never hardcode any of these values anywhere else in the codebase.

```python
import os

# Image pipeline
OCR_CONFIDENCE_THRESHOLD: float = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.85"))

# API keys
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Model IDs (HuggingFace hub)
GEMMA_MODEL_ID: str = os.getenv("GEMMA_MODEL_ID", "google/gemma-4-e2b-it")
QWEN_MODEL_ID: str = os.getenv("QWEN_MODEL_ID", "Qwen/Qwen2.5-Math-1.5B")

# Training
QLORA_R: int = int(os.getenv("QLORA_R", "16"))
QLORA_ALPHA: int = int(os.getenv("QLORA_ALPHA", "32"))
QLORA_DROPOUT: float = float(os.getenv("QLORA_DROPOUT", "0.05"))
TRAIN_BATCH_SIZE: int = int(os.getenv("TRAIN_BATCH_SIZE", "1"))
GRAD_ACCUM_STEPS: int = int(os.getenv("GRAD_ACCUM_STEPS", "4"))

# Paths
DATA_PROCESSED_DIR: str = os.getenv("DATA_PROCESSED_DIR", "data/processed")
MODELS_DIR: str = os.getenv("MODELS_DIR", "models")
EVAL_RESULTS_DIR: str = os.getenv("EVAL_RESULTS_DIR", "evaluation/results")
```

---

## Image Input Pipeline (`pipeline/image_router.py`)

All models process images via the same text-extraction routing strategy:

```
Receive image input
    ↓
    [Step 1] Run PaddleOCR → get confidence score
    ↓
    Confidence >= OCR_CONFIDENCE_THRESHOLD (default 0.85)?
    ├── YES → Use OCR text output directly → return str
    └── NO  →
            [Step 2] Call Gemini Vision to classify image type
            Prompt (Vietnamese):
            "Ảnh này là hình học/hình khối, hay ảnh bài toán có chữ khó đọc,
             hay ảnh minh họa bài toán? Hãy trả lời bằng một trong ba loại:
             'hình học', 'chữ', 'minh họa'."
            ↓
            ├── 'hình học' → Gemini describes geometry (dimensions, shapes) → return str
            ├── 'chữ'     → Gemini transcribes text from image → return str
            └── 'minh họa'→ Gemini describes problem context → return str
```

**Implementation rules:**
- Function signature: `def route_image(image: Union[str, Image.Image]) -> str`
- Wrap all OCR and Gemini calls in `try/except`; on failure, raise a custom `ImageProcessingError` with a descriptive message — never swallow exceptions silently
- Log confidence score and routing decision at `DEBUG` level
- All Gemini prompts must be in Vietnamese

---

## Backend API (`backend/main.py`)

FastAPI app with the following endpoints:

```
POST /solve
  Body:     { "question": str, "model": "m1"|"m2"|"m3"|"m4", "image": str | null }
  Response: { "solution": str, "answer": str, "model": str, "latency_ms": int }

GET /health
  Response: { "status": "ok", "models_loaded": ["m1", "m2", ...] }

POST /compare
  Body:     { "question": str, "image": str | null }
  Response: { "results": [{ "model": str, "solution": str, "answer": str, "latency_ms": int }] }
```

**Rules:**
- `image` field in request body is a base64-encoded string or null; decode to `PIL.Image` before passing to router
- All 4 models must be loadable and callable from the same FastAPI process
- Use `async` endpoints; model inference runs in a thread pool via `asyncio.get_event_loop().run_in_executor()`
- Always measure and return `latency_ms` for every inference call
- Input validation via Pydantic schemas in `schemas.py`
- `/compare` runs all 4 models **concurrently** using `asyncio.gather()` — not sequentially
- On `ImageProcessingError`, return HTTP 422 with body: `{ "error": "IMAGE_PROCESSING_FAILED", "message": "<details>" }` — never raise an unhandled 500
- On any other unexpected exception during inference, return HTTP 500 with `{ "error": "INFERENCE_ERROR", "message": "<details>" }`
- The Gradio frontend is responsible for displaying error messages to the user based on the `error` code — the API must never attempt to re-prompt the user directly

---

## Evaluation (`evaluation/`)

### Primary Metric: Answer Accuracy

Extract the numeric answer from model output and compare to ground truth `right_choice`.

```python
import re

def extract_answer(text: str) -> str:
    """
    Extract the final numeric answer from model output.
    Strategy:
    1. Look for explicit answer keywords first: 'Đáp số:', 'Kết quả:', 'Vậy'
       and extract the number immediately following.
    2. If no keyword found, extract the LAST number in the text.
    3. Normalize: remove commas used as thousands separators,
       strip leading zeros, standardize decimal separator to '.'.
    Examples:
        "Vậy có 72 cái kẹp." → "72"
        "Đáp số: 30,651" → "30651" (or "30.651" if decimal — context-dependent)
        "C. 30,651" → "30651"
        "The answer is 1.5 kg" → "1.5"
    """
    ...
```

### Full Metrics Table

| Metric | Priority | Applied to | Notes |
|--------|----------|------------|-------|
| Answer Accuracy | Primary | All models | Uses `extract_answer()` normalizer |
| Exact Match | Secondary | M1, M2 | Full string match of `answer` field |
| BLEU / ROUGE-L | Secondary | All models | Text quality of CoT solution |
| LLM-as-judge (Gemini) | Secondary | M3, M4 | CoT logical validity score 1–5 |
| Inference speed (ms) | Secondary | All models | Measured per sample, report mean ± std |

### LLM-as-Judge Prompt Template (`evaluation/llm_judge.py`)

```python
JUDGE_PROMPT_TEMPLATE = """
Bạn là giáo viên toán tiểu học. Hãy chấm điểm lời giải sau trên thang điểm 1–5.

Bài toán: {question}
Lời giải của model: {solution}
Đáp án đúng: {right_choice}

Tiêu chí chấm:
- 5: Lời giải đúng, logic rõ ràng, từng bước hợp lý
- 4: Lời giải đúng nhưng thiếu một bước trung gian
- 3: Hướng đi đúng nhưng có sai số nhỏ
- 2: Lời giải sai nhưng có một số bước đúng
- 1: Sai hoàn toàn hoặc không liên quan

Chỉ trả về một số nguyên từ 1 đến 5. Không giải thích thêm.
"""
```

### Evaluation Runner Rules (`evaluation/run_eval.py`)

- Load test set exclusively from `data/processed/test.jsonl`
- Run models in order: M1 → M2 → M3 → M4
- Save per-model results to `evaluation/results/{model_id}_results.json`
- Print a summary comparison table at the end
- Never load training or validation data into the evaluation runner

---

## Coding Conventions

- **Language:** Python 3.10+ with type hints required on all function signatures
- **Vietnamese text:** All prompts, instructions, and data comments remain in Vietnamese
- **Code comments & docstrings:** English only
- **Config values:** Always from `config.py` / environment variables — never hardcoded
- **Logging:** Use Python `logging` module exclusively — never `print()`
- **Dependency additions:** Always note `# poetry add <package>` at the top of any file that introduces a new dependency
- **Each model directory** must have its own `train.ipynb`, `inference.py`, and `README.md`

---

## Agent Task Hints

### Training Task
- Always save checkpoints to `models/{model_id}/checkpoints/`
- Log training loss and learning rate, and export these logs to a CSV file (e.g., `models/{model_id}/logs/train_logs.csv`).
- Save final model to `models/{model_id}/final/`
- Load the dataset (`data_warehouse.csv`) from the Kaggle input path, e.g., `/kaggle/input/` instead of local project paths when writing Kaggle notebooks.
- Plot training and evaluation metrics (e.g., loss curves, accuracy curves), and save these figures to be included in the reporting.
- Export all required files (logs, figures, evaluation results) and zip them into a final report archive for submission.
- For M1/M2: build vocab from `data_warehouse.csv` at the start of training; save to `models/{model_id}/vocab.json`
- For M3/M4 on Kaggle T4: always include `gradient_checkpointing=True`, `per_device_train_batch_size=1`, `gradient_accumulation_steps=4`
- Training code must be written in Kaggle Notebook format (`train.ipynb`). Only text data is used for training.

### Evaluation Task
- Load test set from `data_warehouse.csv`
- Run all 4 models sequentially (memory constraint on single GPU)
- Save results to `evaluation/results/{model_id}_results.json`
- Print a summary table at the end

### Image Pipeline Task
- Always handle `ImageProcessingError` gracefully — propagate it to the API layer as HTTP 422, never swallow
- Never crash the API on image processing failure

