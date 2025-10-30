import unicodedata, re, pathlib, json
from typing import Optional

BASE = pathlib.Path(__file__).resolve().parents[2]
RAW_DIR = BASE / "data" / "raw"
PROC_DIR = BASE / "data" / "processed"

HOMOGLYPHS = {
    'а':'a','с':'c','е':'e','і':'i','о':'o','р':'p','һ':'h','ϲ':'c','ԁ':'d',
    'ⅼ':'l','Ι':'I','ὀ':'o','ᴀ':'a','ḟ':'f','ɪ':'i','ⅼ':'l'
}
CONTROL_CHAR_RE = re.compile(r'[\u0000-\u001F\u007F-\u009F]')

def replace_homoglyphs(text: str) -> str:
    return ''.join(HOMOGLYPHS.get(ch, ch) for ch in text)

def remove_invisible(text: str) -> str:
    text = CONTROL_CHAR_RE.sub('', text)
    text = re.sub(r'[\u200B-\u200F\u202A-\u202E]', '', text)
    return text

def normalize_unicode(text: str) -> str:
    return unicodedata.normalize('NFKC', text)

def collapse_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()

def preprocess_prompt(s: str) -> str:
    if s is None: return s
    s2 = normalize_unicode(s)
    s2 = replace_homoglyphs(s2)
    s2 = remove_invisible(s2)
    s2 = collapse_whitespace(s2)
    return s2

def preprocess_file(input_path: str, output_path: Optional[str]=None):
    inp = pathlib.Path(input_path)
    outp = pathlib.Path(output_path) if output_path else (PROC_DIR / inp.name)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with inp.open('r', encoding='utf-8') as inf, outp.open('w', encoding='utf-8') as outf:
        for line in inf:
            rec = json.loads(line)
            rec['prompt'] = preprocess_prompt(rec.get('prompt'))
            if rec.get('context') is not None:
                rec['context'] = preprocess_prompt(rec.get('context'))
            outf.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return str(outp)

if __name__ == '__main__':
    for p in RAW_DIR.glob('*.jsonl'):
        out = preprocess_file(str(p))
        print('Wrote', out)
