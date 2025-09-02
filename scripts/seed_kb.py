"""
Utility to add new KB docs quickly.
Usage: python scripts/seed_kb.py "Title" "content..."
"""
import os, sys
KB_DIR = "./data/knowledge_base"
os.makedirs(KB_DIR, exist_ok=True)

def main():
    if len(sys.argv) < 3:
        print("Usage: seed_kb.py <title> <content...>")
        return
    title = sys.argv[1].strip().replace(" ","_")
    content = " ".join(sys.argv[2:])
    path = os.path.join(KB_DIR, f"{title}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content+"\n")
    print("Wrote", path)

if __name__ == "__main__":
    main()
