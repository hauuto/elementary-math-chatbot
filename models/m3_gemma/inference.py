import sys
import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

# Make config.py importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import config

_model = None
_tokenizer = None

def load_model():
    global _model, _tokenizer
    if _model is not None:
        return

    try:
        base_model_id = config.GEMMA_MODEL_ID

        # Check both "final" and the base m3_gemma dir for adapter
        adapter_dir_final = os.path.join(config.MODELS_DIR, "m3_gemma", "final")
        adapter_dir_base = os.path.join(config.MODELS_DIR, "m3_gemma")

        if os.path.exists(os.path.join(adapter_dir_final, "adapter_config.json")):
            adapter_dir = adapter_dir_final
        elif os.path.exists(os.path.join(adapter_dir_base, "adapter_config.json")):
            adapter_dir = adapter_dir_base
        else:
            adapter_dir = adapter_dir_final # Fallback

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

        # Load tokenizer
        tokenizer_path = adapter_dir if os.path.exists(adapter_dir) else base_model_id
        _tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        if _tokenizer.pad_token is None:
            _tokenizer.pad_token = _tokenizer.eos_token

        # Load base model
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            quantization_config=bnb_config,
            device_map="auto",
            dtype=torch.bfloat16,
            attn_implementation="sdpa"
        )
        base_model.config.use_cache = True

        if os.path.exists(adapter_dir):
            _model = PeftModel.from_pretrained(base_model, adapter_dir)
        else:
            print(f"Adapter not found at {adapter_dir}, using base model.")
            _model = base_model

        _model.eval()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e

def generate(prompt: str) -> str:
    """
    Generate a solution for the given math problem.
    """
    load_model()

    instruction = "Hãy giải bài toán sau từng bước, trình bày rõ ràng từng bước tính:"

    # Gemma chat template standard format
    formatted_prompt = (
        f"<bos><start_of_turn>user\n"
        f"{instruction}\n"
        f"{prompt}<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )

    inputs = _tokenizer(formatted_prompt, return_tensors="pt").to(_model.device)

    with torch.no_grad():
        print("Starting generation for M3...")
        start_gen = __import__('time').time()
        outputs = _model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=False,
            repetition_penalty=1.1,
            pad_token_id=_tokenizer.pad_token_id,
            eos_token_id=_tokenizer.eos_token_id,
            use_cache=True
        )
        print(f"Generation finished in {__import__('time').time() - start_gen:.2f}s")

    # Extract output without the prompt
    input_length = inputs["input_ids"].shape[1]
    generated_tokens = outputs[0][input_length:]
    generated_text = _tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

    return generated_text
