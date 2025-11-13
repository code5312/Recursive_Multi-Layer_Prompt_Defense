#!/usr/bin/env python
import json, re, random, uuid
from pathlib import Path

SRCs = ["data/raw/attacks.jsonl","data/raw/benign.jsonl"]
OUTA = Path("data/raw/attacks_aug_para.jsonl")
OUTB = Path("data/raw/benign_aug_para.jsonl")

syn = {
  "삭제": ["지워","제거","삭제해"],
  "송금": ["이체","전송","보내"],
  "요약": ["정리","요약해","한줄로"],
  "비밀번호": ["패스워드","PW","비번"],
  "내일": ["익일","다음날","내일 오전"],
}
def perturb(s:str)->str:
    t=s
    for k, vs in syn.items():
        if k in t and random.random()<0.6:
            t=t.replace(k, random.choice(vs))
    # 금액/숫자 변형
    t=re.sub(r"([0-9]{3,})", lambda m: str(int(int(m.group(1))*random.choice([1,1,1,2,3]))), t)
    return t

def proc_file(src, out):
    outl=[]
    for L in Path(src).read_text(encoding="utf-8").splitlines():
        r=json.loads(L)
        txt = r["input"].get("user_text","")
        if not txt.strip(): continue
        new = perturb(txt)
        if new!=txt:
            nr = {**r}
            nr["id"] = f'{r.get("id","rec")}_para_{uuid.uuid4().hex[:6]}'
            nr["input"] = {**r["input"], "user_text": new}
            outl.append(nr)
    Path(out).write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in outl), encoding="utf-8")
    print(f"[OK] {src} → {out} ({len(outl)})")

if __name__=="__main__":
    proc_file(SRCs[0], OUTA)
    proc_file(SRCs[1], OUTB)
