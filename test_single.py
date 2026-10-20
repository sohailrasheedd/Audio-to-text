"""Single upload ka test: job banao, poll karo, text dikhao."""
import sys
import time

import requests

BASE = "http://127.0.0.1:8000"
f = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\dell\Desktop\Audio to text\test_audio\urdu_test3.mp3"

print("health:", requests.get(f"{BASE}/api/health", timeout=10).json())

name = f.rsplit("\\", 1)[-1]
with open(f, "rb") as fh:
    r = requests.post(f"{BASE}/api/jobs",
                      files=[("files", (name, fh, "audio/mpeg"))],
                      data={"language": "ur"}, timeout=120)
print("job:", r.json())
job_id = r.json()["job_id"]

seen = 0
while True:
    d = requests.get(f"{BASE}/api/jobs/{job_id}", params={"after": seen}, timeout=60).json()
    seen += len(d.get("results", []))
    print(f"\r{d['done']}/{d['total']} - {d.get('current')}", end="", flush=True)
    if d["status"] == "done":
        break
    time.sleep(1)

print()
for res in d["results"]:
    if res.get("status") == "error":
        print("ERROR:", res.get("error"))
    else:
        print(f"[{res['filename']}] lang={res['language']} | {res['took_sec']}s")
        print("TEXT:", res["text"])
