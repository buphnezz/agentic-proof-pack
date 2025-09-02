"""
Offline eval harness:
- Reads ./data/golden_set/questions.jsonl
- Calls /ask for each q, aggregates metrics
- Writes ./data/reports/eval.html
"""
import json, os, time, statistics, requests, html
BASE = "http://localhost:8000"
IN = "./data/golden_set/questions.jsonl"
OUT = "./data/reports/eval.html"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

def main():
    qs = []
    with open(IN, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            qs.append(json.loads(line)["q"])

    latencies = []
    grounded = 0
    insufficient = 0
    rows = []
    for q in qs:
        t0 = time.time()
        r = requests.post(f"{BASE}/ask", json={"question": q, "top_k": 3}, timeout=10)
        j = r.json()
        dt = (time.time()-t0)*1000
        latencies.append(dt)
        if not j.get("insufficient_context") and j.get("citations"):
            grounded += 1
        if j.get("insufficient_context"):
            insufficient += 1
        rows.append((q, dt, j.get("insufficient_context"), len(j.get("citations", []))))

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=100)[94]
    p99 = statistics.quantiles(latencies, n=100)[98]
    grounded_ratio = grounded / max(1,len(qs))

    html_rows = "\n".join(
        f"<tr><td>{html.escape(q)}</td><td>{dt:.0f} ms</td><td>{'yes' if ins else 'no'}</td><td>{cites}</td></tr>"
        for q,dt,ins,cites in rows
    )

    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Eval Report</title>
<style>body{{font-family:system-ui}} table{{border-collapse:collapse}} td,th{{border:1px solid #ddd;padding:6px}}</style>
</head><body>
<h2>Eval Report</h2>
<ul>
<li>Questions: {len(qs)}</li>
<li>p50: {p50:.0f} ms</li>
<li>p95: {p95:.0f} ms</li>
<li>p99: {p99:.0f} ms</li>
<li>Grounded ratio: {grounded_ratio:.2f}</li>
<li>Insufficient-context: {insufficient}</li>
</ul>
<table>
<tr><th>Question</th><th>Latency</th><th>Insufficient</th><th>#Citations</th></tr>
{html_rows}
</table>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {OUT}")

if __name__ == "__main__":
    main()
