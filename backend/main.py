import time
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.schemas import SolveRequest, SolveResponse, CompareRequest, CompareResponse, CompareResult, HealthResponse
from pipeline.image_router import route_image, ImageProcessingError
from backend.inference import solve_with_answer

app = FastAPI(title="Vietnamese Elementary Math Chatbot API")

async def run_inference(model: str, prompt: str) -> tuple[str, str, int]:
    start_time = time.time()
    loop = asyncio.get_event_loop()
    sol, ans = await loop.run_in_executor(None, solve_with_answer, model, prompt)
    latency_ms = int((time.time() - start_time) * 1000)
    return sol, ans, latency_ms

@app.post("/solve", response_model=SolveResponse)
async def solve_endpoint(request: SolveRequest):
    try:
        prompt = request.question

        if request.image:
            image_text = route_image(request.image)
            # Append image info
            prompt = f"{prompt}\n[Thông tin từ ảnh]: {image_text}"

        sol, ans, lat = await run_inference(request.model, prompt)

        return SolveResponse(
            solution=sol,
            answer=ans,
            model=request.model,
            latency_ms=lat
        )
    except ImageProcessingError as e:
        return JSONResponse(status_code=422, content={"error": "IMAGE_PROCESSING_FAILED", "message": str(e)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": "INFERENCE_ERROR", "message": str(e)})

@app.post("/compare", response_model=CompareResponse)
async def compare_endpoint(request: CompareRequest):
    try:
        prompt = request.question

        if request.image:
            image_text = route_image(request.image)
            prompt = f"{prompt}\n[Thông tin từ ảnh]: {image_text}"

        models = ["m1", "m2", "m3", "m4"]

        tasks = [run_inference(m, prompt) for m in models]
        responses = await asyncio.gather(*tasks)

        results = []
        for m, (sol, ans, lat) in zip(models, responses):
            results.append(CompareResult(
                model=m,
                solution=sol,
                answer=ans,
                latency_ms=lat
            ))

        return CompareResponse(results=results)
    except ImageProcessingError as e:
        return JSONResponse(status_code=422, content={"error": "IMAGE_PROCESSING_FAILED", "message": str(e)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": "INFERENCE_ERROR", "message": str(e)})

@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="ok",
        models_loaded=["m4"]
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
