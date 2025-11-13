#!/usr/bin/env python
import json, hashlib
from pathlib import Path

def dedup(inp, outp):
    seen=set(); out=[]
    for L in Path(inp).read_text(encoding="utf-8").splitlines():
        r=json.loads(L)
        key=json.dumps({"u":r["input"].get("user_text",""),
                        "h":r["input"].get("context_html",""),
                        "t":sorted(r["input"].get("tools_allowed",[])),
                        "c":r["label"].get("class",""),
                        "a":r["label"].get("attack_type","")}, ensure_ascii=False)
        h=hashlib.sha256(key.encode("utf-8")).hexdigest()
        if h in seen: continue
        seen.add(h); out.append(r)
    Path(outp).write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in out),encoding="utf-8")

if __name__=="__main__":
    dedup("data/raw/attacks.jsonl", "data/raw/attacks.jsonl")
    dedup("data/raw/benign.jsonl",  "data/raw/benign.jsonl")
