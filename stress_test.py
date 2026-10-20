"""Stress test: 500 audio files ek saath server par bhej kar progress dekhein.

Run (server chala hua ho):
  venv\Scripts\python.exe stress_test.py
"""
import sys
import time

import requests

BASE = "http://127.0.0.1:8000"
BATCH_DIR = r"C:\Users\dell\Desktop\Audio to text\test_batch500"


def main():
    files = [
        ("files", (name, open(f"{BATCH_DIR}\\{name}", "rb"), "audio/mpeg"))
        for name in sorted(__import__("os").listdir(BATCH_DIR))
    ]
    print(f"{len(files)} files bheji ja rahi hain...")

    started = time.time()
    r = requests.post(
        f"{BASE}/api/jobs",
        files=files,
        data={"language": "ur", "want_summary": "false"},
        timeout=600,
    )
    for _, fh in files:
        fh[1].close()
    r.raise_for_status()
    job_id = r.json()["job_id"]
    print(f"Job ban gaya: {job_id}")

    seen = 0
    while True:
        data = requests.get(f"{BASE}/api/jobs/{job_id}", params={"after": seen}, timeout=60).json()
        seen += len(data.get("results", []))
        pct = data["done"] / data["total"] * 100
        print(
            f"\r{data['done']}/{data['total']} ({pct:5.1f}%) "
            f"| chal rahi hai: {str(data.get('current'))[:40]:40} "
            f"| ETA: {data.get('eta_text') or '-':15}",
            end="", flush=True,
        )
        if data["status"] == "done":
            break
        time.sleep(2)

    took = time.time() - started
    errors = [r for r in data["results"] if r.get("status") == "error"]
    print(f"\n\nMUKAMMAL - {data['total']} files, waqt: {took/60:.1f} min, errors: {len(errors)}")
    ok = [r for r in data["results"] if r.get("status") == "ok"]
    if ok:
        s = ok[0]
        print(f"\nNamuna ({s['filename']}): {s['text'][:120]}")
    if errors:
        print(f"Pehla masla: {errors[0]}")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        sys.exit("Server chal nahi raha - pehle: python app.py")
