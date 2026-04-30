import gradio as gr
import time
import random

def mock_inference(model: str, text: str, has_image: bool) -> tuple[str, str, int]:
    """Generates a mock response for frontend testing."""
    time.sleep(random.uniform(0.5, 1.5))
    latency = random.randint(500, 1500)
    img_notice = " (Kèm ảnh)" if has_image else ""
    return (
        f"Đây là lời giải giả lập từ mô hình {model}{img_notice} cho câu hỏi:\n {text}\n\nBước 1: Giả sử X.\nBước 2: Phân tích tiếp theo.\nVậy kết quả là...",
        "Đáp án đúng",
        latency
    )

def chat_fn(message, history, model_choice):
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
        for m in ["M1", "M2", "M3", "M4"]:
            sol, ans, lat = mock_inference(m, text, has_image)
            results.append(f"### {m} ({lat}ms)\n{sol}\n\n**Kết quả:** {ans}")
        val = "\n---\n".join(results)
        return val
    else:
        sol, ans, lat = mock_inference(model_choice, text, has_image)
        return f"*(Thời gian xử lý: {lat}ms)*\n\n{sol}\n\n**Kết quả:** {ans}"

with gr.Blocks(title="Vietnamese Math Chatbot", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧮 Vietnamese Elementary Math Chatbot")
    gr.Markdown("Dự án chatbot giải toán tiểu học Việt Nam.\n\nChọn cấu trúc mô hình bên dưới để thử nghiệm.")

    model_dropdown = gr.Dropdown(
        choices=["M1", "M2", "M3", "M4", "Compare"],
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
