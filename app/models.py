from pydantic import BaseModel, Field
from typing import List


class Citation(BaseModel):
    doc_id: str
    start_line: int
    end_line: int
    snippet: str


class Metrics(BaseModel):
    latency_ms: int
    grounded_ratio: float = Field(ge=0.0, le=1.0)
    schema_repairs: int


class AskRequest(BaseModel):
    question: str
    top_k: int = 3


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    metrics: Metrics
    insufficient_context: bool = False
