# Pilot SOW
Acceptance tests:
- Schema-valid responses should be at least 98% without repair, and a further 1–2% after repair.
- Citation coverage should be at least 95% of answers, otherwise the system returns an insufficient context message.
- Latency targets: p95 ≤ 3000 ms and p99 ≤ 5000 ms on a set of 100 queries over a small corpus.
- Audit completeness: 100% of tool calls and citations are logged with a trace identifier.
