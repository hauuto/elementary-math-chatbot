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
├── data/
│   ├── raw/                    # ViMathQA + scraped data (do not modify)
│   │   └── images/             # Raw images referenced by dataset samples
│   ├── synthetic/              # LLM-generated samples (pre-QA)
│   ├── processed/              # Final cleaned dataset after preprocessing pipeline
│   │   ├── train.jsonl
│   │   ├── val.jsonl
│   │   └── test.jsonl
│   └── qa/                     # QA reports and logs
│       └── rejected_log.jsonl
├── models/
│   ├── m1_lstm/
│   │   ├── train.py
│   │   ├── inference.py
│   │   ├── vocab.py            # Vocabulary builder for M1/M2
│   │   └── README.md
│   ├── m2_transformer/
│   │   ├── train.py
│   │   ├── inference.py
│   │   ├── vocab.py
│   │   └── README.md
│   ├── m3_gemma/
│   │   ├── train.py
│   │   ├── inference.py
│   │   └── README.md
│   └── m4_qwen/
│       ├── train.py
│       ├── inference.py
│       └── README.md
├── pipeline/
│   ├── preprocess.py           # Full preprocessing pipeline (raw → processed)
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

Every sample — whether from ViMathQA, scraped, or synthetic — must follow this exact schema:

```json
{
  "question": "string — bài toán đề bài",
  "answer": "string — lời giải CoT từng bước",
  "right_choice": "string — đáp số cuối (số thuần túy nếu tự luận, A/B/C/D nếu trắc nghiệm)",
  "choices": ["list — [\"\"] nếu tự luận, danh sách đáp án nếu trắc nghiệm"],
  "instruction": "string — prompt instruction (e.g. 'Hãy từng bước giải quyết bài toán dưới đây:')",
  "source": "string — một trong: vimathqa | synthetic | manual | scraping",
  "has_image": "boolean",
  "image_path": "string | null — đường dẫn tương đối từ project root"
}
```

**Schema rules (strictly enforced by QA scripts):**
- Never add or remove fields outside this schema
- `right_choice` for tự luận = the numeric answer only — no units, no Vietnamese text (e.g., `"72"` not `"72 cái kẹp"`)
- `choices` for tự luận = `[""]` (a list with exactly one empty string) — never `[]` or `null`
- `source` must be exactly one of: `vimathqa`, `synthetic`, `manual`, `scraping` — no other values, no typos
- `image_path` must be a relative path from project root, e.g., `data/raw/images/img_001.png`
- `has_image` must be `true` if and only if `image_path` is non-null

---

## Data Preprocessing Pipeline (`pipeline/preprocess.py`)

This pipeline runs after all raw data is collected and before any model training. It is the mandatory step that produces the final `data/processed/` splits.

### Pipeline Stages

```
[Stage 1] Load & Merge
    ├── Load ViMathQA samples from data/raw/
    ├── Load scraped/manual samples from data/raw/
    └── Load synthetic samples from data/synthetic/ (post-generation)
           ↓
[Stage 2] Schema Validation
    ├── Validate all required fields are present with correct types
    ├── Check source ∈ {vimathqa, synthetic, manual, scraping}
    ├── Verify has_image ↔ image_path consistency
    └── Log and discard malformed samples → data/qa/rejected_log.jsonl
           ↓
[Stage 3] Text Normalization
    ├── Normalize Unicode (NFC) for Vietnamese text
    ├── Strip leading/trailing whitespace from all string fields
    ├── Normalize right_choice: extract numeric value, remove units and Vietnamese words
    │   e.g., "72 cái kẹp" → "72", "C. 30,651" → "30,651"
    └── Validate right_choice is purely numeric (for tự luận) or A/B/C/D (trắc nghiệm)
           ↓
[Stage 4] Deduplication
    ├── Hash question field (after normalization) to detect exact duplicates
    ├── Optionally: fuzzy dedup using character n-gram similarity (threshold: 0.95)
    └── Keep first occurrence; log removed duplicates count
           ↓
[Stage 5] Test Set Isolation (CRITICAL — run BEFORE synthetic generation to prevent leakage)
    ├── Reserve a stratified split from ViMathQA ONLY as the held-out test set
    ├── Extract test set question hashes BEFORE synthetic generation begins
    ├── At this stage, filter out any synthetic sample whose question hash
    │   has cosine similarity > 0.85 with any test set question
    └── Save test hashes to data/processed/test_hashes.txt for reference
           ↓
[Stage 6] Train / Val / Test Split
    ├── Test set: reserved ViMathQA samples (see Stage 5) — ~5% of total
    ├── Val set: stratified sample from remaining data — ~5% of total
    └── Train set: all remaining samples
           ↓
[Stage 7] Tokenizer Vocab Build (M1 / M2 only)
    ├── Build character-level or word-level vocabulary from train set ONLY
    ├── Save vocab to models/m1_lstm/vocab.json and models/m2_transformer/vocab.json
    └── Vocab must never be built using val or test data
           ↓
[Output] Write data/processed/train.jsonl, val.jsonl, test.jsonl
         Print summary: total samples, split sizes, duplicate count, rejected count
```

**Implementation rules for `preprocess.py`:**
- Accept `--input-dir`, `--output-dir`, and `--seed` as CLI arguments (use `argparse`)
- All stages must be idempotent — safe to re-run
- Log every stage's start, end, and item count using Python `logging`
- Stage 5 (test isolation) must log a warning if any synthetic sample is filtered out due to overlap

---

## Model Architecture Overview

| ID | Name | Type | Framework | Notes |
|----|------|------|-----------|-------|
| M1 | LSTM Language Model | From scratch | PyTorch | Text generation, no attention |
| M2 | Transformer Decoder | From scratch | PyTorch | Standard decoder-only architecture |
| M3 | Gemma 4 E4B + QLoRA | Fine-tuned | HuggingFace + PEFT | Multimodal — handles image input natively |
| M4 | Qwen2.5-Math-7B + QLoRA | Fine-tuned | HuggingFace + PEFT | Math-specialized, text-only |

**Research question for M3 vs M4:** Trade-off between multimodal capability (M3) and math domain specialization (M4).

### Common Inference Interface

All 4 models must expose this interface in their respective `inference.py`:

```python
from PIL import Image
from typing import Optional, Union

def generate(prompt: str, image: Optional[Union[str, Image.Image]] = None) -> str:
    """
    Generate a solution for the given math problem.

    Args:
        prompt: The math problem text (Vietnamese).
        image: Optional image input. Only M3 (Gemma) uses this parameter.
                M1, M2, M4 must raise ValueError if image is passed.
    Returns:
        The generated solution string (Vietnamese CoT).
    """
    ...
```

**Additional rules per model type:**
- M1 and M2: pure PyTorch only, no HuggingFace Trainer
- M1 and M2: must load vocab from their respective `vocab.json` at inference time
- M3 and M4: always use `peft` with `LoraConfig`, `bitsandbytes` for 4-bit quantization, and `trl.SFTTrainer`
- M1 and M2: raise `ValueError("Image input not supported for this model")` if `image` is not None

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
GEMMA_MODEL_ID: str = os.getenv("GEMMA_MODEL_ID", "google/gemma-4-e4b")
QWEN_MODEL_ID: str = os.getenv("QWEN_MODEL_ID", "Qwen/Qwen2.5-Math-7B")

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

Three input types, three routing strategies:

```
Receive image input + model_id
    ↓
Is model_id == "m3"?
    ├── YES → M3 Bypass: return image object directly (no OCR, no Gemini)
    └── NO  →
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
- Function signature: `def route_image(image: Union[str, Image.Image], model_id: str) -> Union[str, Image.Image]`
- Return type is `Image.Image` only for M3 bypass; all other paths return `str`
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
- **Each model directory** must have its own `train.py`, `inference.py`, and `README.md`

---

## Agent Task Hints

When asked to implement a specific component, follow these patterns:

### Data Generation Task (`scripts/generate_synthetic.py`)
- Read seed questions from `data/raw/`
- Call Gemini API with batch prompts
- Validate output against schema before saving
- Log rejected samples to `data/qa/rejected_log.jsonl`
- Do NOT generate questions that overlap with test set hashes in `data/processed/test_hashes.txt`

### Preprocessing Task (`pipeline/preprocess.py`)
- Always run all 7 stages in order
- Stage 5 (test isolation) must run even if synthetic data has not been generated yet — it pre-computes and saves test hashes
- Print a final summary: `[Preprocess] Done. Train: N, Val: N, Test: N, Rejected: N, Deduped: N`

### Training Task
- Always save checkpoints to `models/{model_id}/checkpoints/`
- Log training loss to `models/{model_id}/logs/`
- Save final model to `models/{model_id}/final/`
- For M1/M2: build vocab from `data/processed/train.jsonl` at the start of training; save to `models/{model_id}/vocab.json`
- For M3/M4 on Kaggle T4: always include `gradient_checkpointing=True`, `per_device_train_batch_size=1`, `gradient_accumulation_steps=4`

### Evaluation Task
- Load test set from `data/processed/test.jsonl`
- Run all 4 models sequentially (memory constraint on single GPU)
- Save results to `evaluation/results/{model_id}_results.json`
- Print a summary table at the end

### Image Pipeline Task
- Always handle `ImageProcessingError` gracefully — propagate it to the API layer as HTTP 422, never swallow
- Never crash the API on image processing failure
- M3 bypass logic must be the first check before any OCR or Gemini call