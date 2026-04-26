import json
import sys
import time


def log_debug(enabled, event, **fields):
    if not enabled:
        return
    record = {"ts": round(time.time(), 3), "event": event}
    record.update(fields)
    sys.stderr.write(json.dumps(record, sort_keys=True) + "\n")
