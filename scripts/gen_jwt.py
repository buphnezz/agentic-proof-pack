"""
Generate a HS256 JWT for an email.
Usage:
  export JWT_SECRET=super-secret
  python scripts/gen_jwt.py --email jeff@example.com --mins 120
"""
import os, time, argparse, jwt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--mins", type=int, default=120)
    args = ap.parse_args()

    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise SystemExit("Set JWT_SECRET in env")
    now = int(time.time())
    payload = {"email": args.email, "iat": now, "exp": now + args.mins*60, "scope": ["demo"]}
    token = jwt.encode(payload, secret, algorithm="HS256")
    print(token)

if __name__ == "__main__":
    main()
