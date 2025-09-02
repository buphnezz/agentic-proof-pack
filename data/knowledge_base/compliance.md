# Compliance & Audit
The system records each request and response with a `trace_id` in a JSONL audit file.
Every grounded answer includes citations with document id and line offsets.
If insufficient context is detected, the system returns a safe message instead of fabricating details.
