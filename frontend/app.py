import gradio as gr
import asyncio
import random

MODEL_NAMES = {
    "M1": "M1: LSTM",
    "M2": "M2: Transformer Decoder",
    "M3": "M3: Gemma 4 E4B",
    "M4": "M4: Qwen2.5-Math-7B"
}

async def mock_inference(model: str, text: str, has_image: bool) -> tuple[str, str, int, bool]:
    """Generates a mock response for frontend testing."""
    await asyncio.sleep(random.uniform(0.5, 1.5))
    latency = random.randint(500, 1500)
    img_notice = " (Kèm ảnh)" if has_image else ""
    is_correct = random.choice([True, False])
    ans_text = "Đáp án đúng" if is_correct else "Đáp án sai"
    return (
        f"Đây là lời giải giả lập từ mô hình {model}{img_notice} cho câu hỏi:\n {text}\n\nBước 1: Giả sử X.\nBước 2: Phân tích tiếp theo.\nVậy kết quả là...",
        ans_text,
        latency,
        is_correct
    )

async def chat_fn(message, history, model_choice):
    """
    Handles chat messages and routes them to the mock inference function.
    Supports multimodal inputs (text + images).
    """
    text = message.get("text", "")
    files = message.get("files", [])
    has_image = len(files) > 0

    if not text and not has_image:
        return "Vui lòng nhập câu hỏi hoặc tải lên một hình ảnh."

    if model_choice == "Compare":
        results = []
        tasks = [mock_inference(MODEL_NAMES[m], text, has_image) for m in ["M1", "M2", "M3", "M4"]]
        responses = await asyncio.gather(*tasks)

        val = ""
        for m, (sol, ans, lat, is_correct) in zip(["M1", "M2", "M3", "M4"], responses):
            color = "green" if is_correct else "red"
            model_display_name = MODEL_NAMES[m]
            val += f"""
<details style="margin-bottom: 10px; border: 1px solid #ccc; padding: 8px; border-radius: 5px;">
    <summary style="font-weight: bold; cursor: pointer; color: {color};">
        {model_display_name} ({lat}ms) - {ans}
    </summary>
    <div style="margin-top: 10px; padding-left: 10px; border-left: 3px solid #eee;">
        {sol.replace(chr(10), '<br>')}
        <br><br><b>Kết quả:</b> <span style="color: {color};">{ans}</span>
    </div>
</details>
"""
        return val
    else:
        # Extract ID if a full name was passed from dropdown
        model_name = model_choice if model_choice not in MODEL_NAMES else MODEL_NAMES[model_choice]
        sol, ans, lat, is_correct = await mock_inference(model_name, text, has_image)
        color = "green" if is_correct else "red"
        return f"*(Thời gian xử lý: {lat}ms)*\n\n{sol}\n\n**Kết quả:** <span style='color: {color};'>{ans}</span>"

with gr.Blocks(title="Vietnamese Math Chatbot", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧮 Vietnamese Elementary Math Chatbot")
    gr.Markdown("Dự án chatbot giải toán tiểu học Việt Nam.\n\nChọn cấu trúc mô hình bên dưới để thử nghiệm.")

    # Convert mapping to a list of choices for the dropdown, keeping "Compare"
    dropdown_choices = list(MODEL_NAMES.values()) + ["Compare"]

    model_dropdown = gr.Dropdown(
        choices=dropdown_choices,
        value="Compare",
        label="Chọn Mô hình (Model)",
        interactive=True
    )

    chat_interface = gr.ChatInterface(
        fn=chat_fn,
        multimodal=True,
        additional_inputs=[model_dropdown]
    )

if __name__ == "__main__":
    demo.launch()
