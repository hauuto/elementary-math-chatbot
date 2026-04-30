import os
import csv
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainerCallback,
    TrainingArguments
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
import sys

# Import config (modify path to find config.py at root)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import config

# poetry add datasets trl

class CSVLogCallback(TrainerCallback):
    """Custom callback to log to CSV file"""
    def __init__(self, log_path):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        # Create header if file doesn't exist
        if not os.path.exists(self.log_path):
            with open(self.log_path, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['step', 'epoch', 'loss', 'learning_rate'])

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        if "loss" in logs:
            with open(self.log_path, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    state.global_step,
                    round(state.epoch, 2) if state.epoch else '',
                    round(logs["loss"], 4),
                    logs.get("learning_rate", "")
                ])

def train():
    # Load model and tokenizer
    model_id = config.QWEN_MODEL_ID

    # 4-bit quantization config (Kaggle T4 optimal)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto"
    )

    model = prepare_model_for_kbit_training(model)

    # QLoRA config
    peft_config = LoraConfig(
        r=config.QLORA_R,
        lora_alpha=config.QLORA_ALPHA,
        lora_dropout=config.QLORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"] # Qwen targets are similar
    )

    model = get_peft_model(model, peft_config)

    # Example to load dataset (Assume HuggingFace datasets library format mapped from jsonl)
    from datasets import load_dataset
    data_path = os.path.join(config.DATA_PROCESSED_DIR, "train.jsonl")
    if not os.path.exists(data_path):
        print(f"Dataset not found at {data_path}. Please run preprocessing first.")
        return

    dataset = load_dataset('json', data_files={'train': data_path})['train']

    # Formatting prompt for SFT
    def formatting_prompts_func(example):
        output_texts = []
        for i in range(len(example['question'])):
            text = f"Câu hỏi: {example['question'][i]}\nTrình bày các bước giải:\n{example['answer'][i]}"
            output_texts.append(text)
        return output_texts

    # Set up training arguments enforcing hardware constraints
    output_dir = os.path.join(config.MODELS_DIR, "m4_qwen/checkpoints")
    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=config.TRAIN_BATCH_SIZE, # 1 for T4
        gradient_accumulation_steps=config.GRAD_ACCUM_STEPS, # 4 for T4
        gradient_checkpointing=True,                         # True for T4
        optim="paged_adamw_8bit",                            # 8-bit Adam for T4
        learning_rate=2e-4,
        max_steps=500, # Or set num_train_epochs
        logging_steps=10,
        save_steps=100,
        fp16=True,
    )

    # CSV Log path
    csv_log_path = os.path.join(config.MODELS_DIR, "m4_qwen/logs/training_log.csv")
    csv_callback = CSVLogCallback(log_path=csv_log_path)

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=training_args,
        peft_config=peft_config,
        formatting_func=formatting_prompts_func,
        callbacks=[csv_callback]
    )

    print("Starting training M4 Qwen...")
    trainer.train()

    # Save final model
    final_output_dir = os.path.join(config.MODELS_DIR, "m4_qwen/final")
    trainer.model.save_pretrained(final_output_dir)
    tokenizer.save_pretrained(final_output_dir)
    print(f"Training complete. Model saved to {final_output_dir}")

if __name__ == "__main__":
    train()
