"""
Read emails.csv and emit login links to your Vercel UI with JWT in fragment (not sent to server logs).
CSV format: email
Usage:
  export JWT_SECRET=super-secret
  python scripts/invite_tokens.py --ui https://your-demo.vercel.app
"""
import csv, os, time, argparse, jwt, urllib.parse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="emails.csv")
    ap.add_argument("--ui", required=True)  # e.g. https://agentic-proof.vercel.app
    ap.add_argument("--mins", type=int, default=120)
    args = ap.parse_args()

    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise SystemExit("Set JWT_SECRET")
    now = int(time.time())
    with open(args.csv, newline="") as f:
        r = csv.reader(f)
        for row in r:
            if not row: continue
            email = row[0].strip()
            payload = {"email": email, "iat": now, "exp": now + args.mins*60, "scope": ["demo"]}
            token = jwt.encode(payload, secret, algorithm="HS256")
            print(f"{email}, {args.ui}#token={urllib.parse.quote(token)}")

if __name__ == "__main__":
    main()
