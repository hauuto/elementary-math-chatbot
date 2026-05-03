import sys
import os
import httpx # poetry add httpx
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from evaluation.metrics import extract_answer
import config

def generate(model_name: str, prompt: str) -> str:
    """
    Unified inference for all 4 models.
    """
    model_name = model_name.lower()

    if config.COLAB_API_URL:
        # Request inference from remote Colab server
        try:
            # We don't need async here since FastAPI runs this logic in thread pool wrapper
            with httpx.Client(timeout=600) as client:
                resp = client.post(
                    f"{config.COLAB_API_URL}/generate",
                    json={"model": model_name, "prompt": prompt}
                )
                resp.raise_for_status()
                return resp.json()["solution"]
        except Exception as e:
            raise RuntimeError(f"Lỗi khi gọi API Colab: {e}")

    if model_name == "m4":
        from models.m4_qwen.inference import generate as generate_m4
        return generate_m4(prompt)
    elif model_name == "m3":
        from models.m3_gemma.inference import generate as generate_m3
        return generate_m3(prompt)
    elif model_name == "m1":
        # Placeholder
        return "M1 solution: \nBước 1: 1+1=2.\nVậy đáp số: 2."
    elif model_name == "m2":
        # Placeholder
        return "M2 solution: \nBước 1: 1+1=2.\nVậy đáp số: 2."
    else:
        raise ValueError(f"Unknown model: {model_name}")

def solve_with_answer(model_name: str, prompt: str) -> tuple[str, str]:
    """Generates the solution and extracts the final answer."""
    sol = generate(model_name, prompt)
    ans = extract_answer(sol)
    return sol, ans
