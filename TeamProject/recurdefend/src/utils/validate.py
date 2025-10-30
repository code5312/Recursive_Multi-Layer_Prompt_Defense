import json, pathlib, sys
import jsonschema

BASE = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = BASE / "data" / "schemas" / "sample.schema.json"

def load_schema(path=None):
    p = SCHEMA_PATH if path is None else pathlib.Path(path)
    return json.load(open(p, "r", encoding="utf-8"))

def validate_record(rec, schema=None):
    if schema is None:
        schema = load_schema()
    jsonschema.validate(rec, schema)

def validate_file(jsonl_path, schema=None):
    p = pathlib.Path(jsonl_path)
    errors = []
    for i, line in enumerate(open(p, encoding='utf-8'), start=1):
        try:
            rec = json.loads(line)
            validate_record(rec, schema)
        except Exception as e:
            errors.append((i, str(e), line.strip()[:200]))
    return errors

def main():
    schema = load_schema()
    data_dir = BASE / 'data' / 'raw'
    jsonl_files = list(data_dir.glob('*.jsonl'))
    if not jsonl_files:
        print('No jsonl files found under', data_dir)
        return 1
    any_errors = False
    for f in jsonl_files:
        errs = validate_file(f, schema)
        if errs:
            any_errors = True
            print(f'Validation errors in {f}:')
            for ln, err, snippet in errs[:10]:
                print(f'  line {ln}: {err} -- snippet: {snippet}')
        else:
            print(f'OK: {f}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
