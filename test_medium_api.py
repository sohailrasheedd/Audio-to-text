"""Medium model API test - user ki asli file."""
import io
import json
import sys
import time
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SRC = Path(r"C:\Users\dell\Downloads\WhatsApp Ptt 2026-10-20 at 1.10.23 PM.ogg")
API = "http://127.0.0.1:8000"

with open(SRC, "rb") as f:
    r = requests.post(
        f"{API}/api/jobs",
        files={"files": (SRC.name, f, "audio/ogg")},
        data={"language": "ur", "model": "medium", "want_summary": "false"},
    )
job = r.json()
print("job:", job)
jid = job["job_id"]

t0 = time.time()
last = 0
while True:
    s = requests.get(f"{API}/api/jobs/{jid}?after={last}").json()
    last += len(s.get("results", []))
    if s["status"] in ("done", "cancelled"):
        break
    print(f"  ... {s['done']}/{s['total']} {s['current'] or ''} "
          f"({time.time() - t0:.0f}s)", flush=True)
    time.sleep(20)

out = Path(r"C:\Users\dell\AppData\Local\Temp\opencode\medium_api_result.json")
out.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
print("status:", s["status"], "errors:", s["errors"])
for res in s.get("results", []):
    print("TEXT:", res.get("text"))
