import gradio as gr
import asyncio
import httpx
import base64
import yaml
import os

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

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

async def chat_fn(message, history, model_choice):
    """
    Handles chat messages and routes them to the real inference API.
    Supports multimodal inputs (text + images).
    """
    text = message.get("text", "")
    files = message.get("files", [])
    has_image = len(files) > 0

    if not text and not has_image:
        return "Vui lòng nhập câu hỏi hoặc tải lên một hình ảnh."

    image_b64 = None
    if has_image:
        try:
            with open(files[0], "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"Không thể đọc ảnh: {e}"

    async with httpx.AsyncClient(timeout=600) as client:
        if model_choice == "Compare":
            try:
                resp = await client.post(
                    f"{API_URL}/compare",
                    json={"question": text, "image": image_b64}
                )
                if resp.status_code == 422:
                    return f"Lỗi xử lý ảnh: {resp.json().get('message')}"
                if resp.status_code != 200:
                    return f"Lỗi server: {resp.json().get('message')}"

                data = resp.json()["results"]
                val = ""
                for res in data:
                    m = res["model"].upper()
                    sol = res["solution"]
                    ans = res["answer"]
                    lat = res["latency_ms"]
                    model_display_name = MODEL_NAMES.get(m, m)

                    val += f"""
<details style="margin-bottom: 10px; border: 1px solid #ccc; padding: 8px; border-radius: 5px;">
    <summary style="font-weight: bold; cursor: pointer; color: blue;">
        {model_display_name} ({lat}ms) - {ans}
    </summary>
    <div style="margin-top: 10px; padding-left: 10px; border-left: 3px solid #eee;">
        {sol.replace(chr(10), '<br>')}
        <br><br><b>Kết quả:</b> <span style="color: blue;">{ans}</span>
    </div>
</details>
"""
                return val
            except Exception as e:
                return f"Lỗi gọi API: {e}"
        else:
            # Extract id
            m_key = "m4"
            for k, v in MODEL_NAMES.items():
                if v == model_choice:
                    m_key = k.lower()
                    break

            try:
                resp = await client.post(
                    f"{API_URL}/solve",
                    json={"question": text, "model": m_key, "image": image_b64}
                )
                if resp.status_code == 422:
                    return f"Lỗi xử lý ảnh: {resp.json().get('message')}"
                if resp.status_code != 200:
                    return f"Lỗi server: {resp.json().get('message')}"

                data = resp.json()
                sol = data["solution"]
                ans = data["answer"]
                lat = data["latency_ms"]

                return f"*(Thời gian xử lý: {lat}ms)*\n\n{sol}\n\n**Kết quả:** <span style='color: blue;'>{ans}</span>"
            except Exception as e:
                return f"Lỗi gọi API: {e}"

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
