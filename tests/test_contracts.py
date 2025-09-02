import json
from pydantic import ValidationError
from app.models import AskRequest, AskResponse, Citation, Metrics

def test_models_roundtrip():
    req = AskRequest(question="test", top_k=3)
    # Mimic an answer
    resp = AskResponse(
        answer="x",
        citations=[Citation(doc_id="a.md", start_line=0, end_line=1, snippet="hi")],
        metrics=Metrics(latency_ms=12, grounded_ratio=1.0, schema_repairs=0),
        insufficient_context=False
    )
    j = json.loads(resp.model_dump_json())
    assert "answer" in j and "citations" in j and "metrics" in j
