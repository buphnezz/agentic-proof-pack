"""
Tiny load test using Python threads.
Example: python scripts/load_test.py -c 50 -n 500
"""
import argparse, threading, time, requests, random, json

def worker(base, q, n, latencies):
    for _ in range(n):
        t0=time.time()
        try:
            r=requests.post(f"{base}/ask", json={"question": q, "top_k":3}, timeout=10)
            r.raise_for_status()
        except Exception:
            pass
        latencies.append((time.time()-t0)*1000)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c","--concurrency", type=int, default=20)
    ap.add_argument("-n","--requests", type=int, default=200)
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args()

    per = max(1, args.requests // args.concurrency)
    qs = [
        "What are the acceptance tests for the pilot?",
        "How does the system ensure auditability?",
        "What are the latency targets?"
    ]
    lats=[]
    threads=[]
    for i in range(args.concurrency):
        t=threading.Thread(target=worker, args=(args.base, random.choice(qs), per, lats))
        t.start(); threads.append(t)
    for t in threads: t.join()
    if not lats:
        print("No latencies recorded.")
        return
    lats.sort()
    p50=lats[int(0.5*len(lats))]
    p95=lats[int(0.95*len(lats))-1]
    p99=lats[int(0.99*len(lats))-1]
    print(f"Requests: ~{len(lats)}  p50={p50:.0f}ms  p95={p95:.0f}ms  p99={p99:.0f}ms")

if __name__ == "__main__":
    main()
