from pydantic import BaseModel
from typing import Optional, List

class SolveRequest(BaseModel):
    question: str
    model: str
    image: Optional[str] = None

class SolveResponse(BaseModel):
    solution: str
    answer: str
    model: str
    latency_ms: int

class CompareRequest(BaseModel):
    question: str
    image: Optional[str] = None

class CompareResult(BaseModel):
    model: str
    solution: str
    answer: str
    latency_ms: int

class CompareResponse(BaseModel):
    results: List[CompareResult]

class HealthResponse(BaseModel):
    status: str
    models_loaded: List[str]
