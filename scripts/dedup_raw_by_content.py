# scripts/dedup_raw_by_content.py
import json, hashlib
from pathlib import Path

RAW = Path("data/raw")
def load(p):
    arr=[]
    for L in p.read_text(encoding="utf-8").splitlines():
        if not L.strip(): continue
        arr.append(json.loads(L))
    return arr

def k(r):
    u=(r["input"].get("user_text") or "").strip()
    h=(r["input"].get("context_html") or "").strip()
    return hashlib.sha256((u+"\n"+h).encode("utf-8")).hexdigest()

for name in ["attacks","benign"]:
    p = RAW / f"{name}.jsonl"
    if not p.exists(): 
        print("[MISS]", p); 
        continue
    seen=set(); out=[]
    for r in load(p):
        kk=k(r)
        if kk in seen: 
            continue
        seen.add(kk); out.append(r)
    (RAW / f"{name}_dedup.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in out),
        encoding="utf-8"
    )
    print(f"[OK] {name} -> {name}_dedup.jsonl ({len(out)})")
