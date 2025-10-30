import json, time, uuid, sys

def log_event(event_type, **kwargs):
    rec = {"ts": time.time(), "event": event_type, "rid": str(uuid.uuid4())}
    rec.update(kwargs)
    print(json.dumps(rec, ensure_ascii=False), file=sys.stdout)
