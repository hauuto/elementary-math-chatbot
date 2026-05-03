import os
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

# Image pipeline
OCR_CONFIDENCE_THRESHOLD: float = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.85"))

# API keys
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# LM Studio
LM_STUDIO_URL: str = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")

# Colab bridging URL
COLAB_API_URL: str = os.getenv("COLAB_API_URL", "")

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
