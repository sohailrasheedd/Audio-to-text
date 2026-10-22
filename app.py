"""
Voice to Text - Hybrid Server (Local + Cloud API)
Portfolio Edition
"""
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "transcripts"
JOBS_DIR = OUT_DIR / "jobs"
WHISPER_DIR = BASE_DIR / "whisper_bin"
GGML_DIR = Path(os.getenv("GGML_DIR", BASE_DIR / "models"))

OUT_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)
WHISPER_DIR.mkdir(exist_ok=True)
GGML_DIR.mkdir(exist_ok=True)

def find_whisper_cli() -> Path:
    env_cli = os.getenv("WHISPER_CLI")
    if env_cli and Path(env_cli).exists():
        return Path(env_cli)
    candidates = [
        WHISPER_DIR / "whisper-cli.exe",
        WHISPER_DIR / "main.exe",
        BASE_DIR / "whisper-cli.exe",
        BASE_DIR / "main.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    return WHISPER_DIR / "whisper-cli.exe"

def find_ffmpeg() -> str | None:
    local_candidates = [
        WHISPER_DIR / "ffmpeg.exe",
        BASE_DIR / "ffmpeg.exe",
        BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for c in local_candidates:
        if c.exists():
            return str(c)
    return shutil.which("ffmpeg")

MODELS = {
    "base": "ggml-base.bin",
    "small": "ggml-small-q5_1.bin",
    "medium": "ggml-medium-q5_0.bin",
}

THREADS = int(os.getenv("WHISPER_THREADS", "4"))
WORKERS = int(os.getenv("WHISPER_WORKERS", "1"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

URDU_PROMPT = "یہ ایک اردو آڈیو پیغام ہے۔"

app = FastAPI(title="Voice to Text Server - Hybrid Edition")

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.RLock()
TASK_QUEUE: "queue.Queue[tuple]" = queue.Queue()

def get_available_models() -> dict[str, Path]:
    found = {}
    for k, filename in MODELS.items():
        p = GGML_DIR / filename
        if p.exists():
            found[k] = p
    for p in GGML_DIR.glob("*.bin"):
        if p.name in [x.name for x in found.values()]:
            continue
        key = p.stem.replace("ggml-", "")
        found[key] = p
    return found

def fmt_time(seconds: float) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m:02d}:{s:02d}"

def fmt_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ghanta {m} min"
    if m:
        return f"{m} min {s} sec"
    return f"{s} sec"

def safe_name(name: str) -> str:
    name = Path(name or "audio").name
    return re.sub(r'[<>:"/\\|?*]', "_", name) or "audio.ogg"

def summarize(text: str) -> str | None:
    prompt = (
        "Neeche ek voice message ka text hai. Is ka mukhtasar khulasa Roman Urdu mein likho: "
        "kis ne kya kaha, koi zaroori baat, tareekh, raqam ya kaam jo karna hai. "
        "Sirf wohi likho jo text mein hai, apni taraf se kuch mat barhao.\n\n"
        f"{text}"
    )
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=180,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception:
        return None

def to_wav(src: Path, dst_dir: Path) -> Path:
    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        if src.suffix.lower() == ".wav":
            return src
        raise RuntimeError(
            "FFmpeg nahi mila! MP3/OGG/OPUS/M4A files chalane ke liye ffmpeg.exe ko 'whisper_bin' folder mein rakhein."
        )
    dst = dst_dir / "converted_16k.wav"
    r = subprocess.run(
        [
            ffmpeg_bin, "-y", "-i", str(src),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)
        ],
        capture_output=True,
        timeout=300,
    )
    if r.returncode != 0 or not dst.exists():
        err_msg = r.stderr.decode("utf-8", "ignore")[-300:]
        raise RuntimeError(f"Audio convert nahi ho saki (FFmpeg error): {err_msg}")
    return dst

def transcribe_cloud(path: Path, language: str, api_key: str, provider: str = "groq") -> dict:
    started = time.time()
    base_url = "https://api.groq.com/openai/v1/audio/transcriptions"
    model_name = "whisper-large-v3"
    if provider == "openai":
        base_url = "https://api.openai.com/v1/audio/transcriptions"
        model_name = "whisper-1"

    headers = {"Authorization": f"Bearer {api_key}"}
    
    with tempfile.TemporaryDirectory(prefix="vtt_cloud_") as tmp:
        tmp_dir = Path(tmp)
        audio_wav = to_wav(path, tmp_dir)
        
        with open(audio_wav, "rb") as f:
            files = {"file": (audio_wav.name, f, "audio/wav")}
            data = {"model": model_name, "response_format": "verbose_json"}
            if language and language != "auto":
                data["language"] = language
            
            r = requests.post(base_url, headers=headers, files=files, data=data, timeout=120)
            
            if r.status_code != 200:
                err_text = r.json().get("error", {}).get("message", r.text) if "{" in r.text else r.text
                raise RuntimeError(f"Cloud API Error ({r.status_code}): {err_text}")
            
            resp = r.json()
    
    text = resp.get("text", "").strip()
    duration = resp.get("duration", 0)
    segs = []
    for s in resp.get("segments", []):
        segs.append({
            "start": fmt_time(s.get("start", 0)),
            "end": fmt_time(s.get("end", 0)),
            "text": s.get("text", "").strip()
        })
        
    return {
        "language": resp.get("language") or language or "ur",
        "duration": fmt_time(duration),
        "took_sec": round(time.time() - started, 1),
        "text": text,
        "segments": segs,
    }

def transcribe_one(path: Path, language: str, model_path: Path) -> dict:
    started = time.time()
    whisper_cli = find_whisper_cli()
    if not whisper_cli.exists():
        raise RuntimeError(f"whisper-cli.exe nahi mila! Isay '{WHISPER_DIR}' mein rakhein.")
    if not model_path or not model_path.exists():
        raise RuntimeError(f"Model file nahi mili: {model_path}")

    with tempfile.TemporaryDirectory(prefix="vtt_") as tmp:
        tmp_dir = Path(tmp)
        audio = to_wav(path, tmp_dir)
        out_base = tmp_dir / "out"

        cmd = [
            str(whisper_cli),
            "-m", str(model_path),
            "-f", str(audio),
            "-t", str(THREADS),
            "-oj",
            "-of", str(out_base),
        ]
        if language == "auto":
            cmd += ["--language", "auto"]
        else:
            cmd += ["--language", language]
            if language == "ur":
                cmd += ["--prompt", URDU_PROMPT]

        out_log = tmp_dir / "stdout.log"
        err_log = tmp_dir / "stderr.log"
        with open(out_log, "wb") as fo, open(err_log, "wb") as fe:
            r = subprocess.run(cmd, stdout=fo, stderr=fe, timeout=3600)

        json_path = out_base.with_suffix(".json")
        if r.returncode != 0 or not json_path.exists():
            err = err_log.read_text("utf-8", "ignore")[-400:] + "\n" + out_log.read_text("utf-8", "ignore")[-200:]
            raise RuntimeError(f"whisper-cli fail ({r.returncode}): {err.strip()}")

        data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))

    segs = []
    for s in data.get("transcription", []):
        frm = s.get("offsets", {}).get("from", 0) / 1000.0
        to = s.get("offsets", {}).get("to", 0) / 1000.0
        text = (s.get("text") or "").strip()
        if text:
            segs.append({
                "start": frm,
                "end": to,
                "start_fmt": fmt_time(frm),
                "end_fmt": fmt_time(to),
                "text": text
            })

    full_text = " ".join(s["text"] for s in segs).strip()
    trans_list = data.get("transcription") or []
    dur_ms = trans_list[-1].get("offsets", {}).get("to", 0) if trans_list else 0

    return {
        "language": data.get("result", {}).get("language") or (language or "ur"),
        "duration": fmt_time(dur_ms / 1000.0),
        "took_sec": round(time.time() - started, 1),
        "text": full_text,
        "segments": segs,
    }

def worker_loop():
    while True:
        job_id, idx = TASK_QUEUE.get()
        try:
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job is None or job["status"] == "cancelled":
                    continue
                stored = job["files"][idx]
                job["current"] = stored["name"]

            path = Path(stored["path"])
            entry = {"index": idx, "filename": stored["name"]}

            try:
                if job.get("mode") == "cloud":
                    if not job.get("api_key"):
                        raise ValueError("Cloud API Key missing! Kripya API key darj karein.")
                    res = transcribe_cloud(path, job["language"], job["api_key"], job["api_provider"])
                else:
                    res = transcribe_one(path, job["language"], job["model_path"])
                    
                entry.update(res)
                entry["status"] = "ok"

                txt_stem = re.sub(r'[<>:"/\\|?*]', "_", Path(stored["name"]).stem)
                txt_path = job["dir"] / f"{idx + 1:04d}_{txt_stem}.txt"
                txt_path.write_text(res["text"] or "(koi awaaz nahi mili)", encoding="utf-8")

                if job["want_summary"] and res["text"]:
                    summary = summarize(res["text"])
                    entry["summary"] = summary
                    entry["summary_unavailable"] = summary is None
            except Exception as e:
                entry["status"] = "error"
                entry["error"] = str(e)

            with JOBS_LOCK:
                if job["status"] != "cancelled":
                    job["results"].append(entry)
                    job["done"] += 1
                    if entry.get("status") == "error":
                        job["errors"] += 1
                    if job["done"] >= job["total"]:
                        job["status"] = "done"
                        job["current"] = None
                        job["finished_at"] = time.time()
                        all_path = job["dir"] / "all.txt"
                        all_path.write_text(build_all_text(job), encoding="utf-8")
        finally:
            TASK_QUEUE.task_done()

for _ in range(WORKERS):
    threading.Thread(target=worker_loop, daemon=True).start()

def build_all_text(job: dict) -> str:
    lines = []
    for r in sorted(job["results"], key=lambda x: x["index"]):
        lines.append(f"===== {r['filename']} =====")
        if r.get("status") == "error":
            lines.append(f"[ERROR: {r.get('error')}]")
        else:
            lines.append(r.get("text") or "(koi awaaz nahi mili)")
            if r.get("summary"):
                lines.append(f"\n[Khulasa]: {r['summary']}")
        lines.append("")
    return "\n".join(lines)

def job_public(job: dict, after: int = 0) -> dict:
    with JOBS_LOCK:
        results = job["results"][after:]
        done, total = job["done"], job["total"]
        end_time = job.get("finished_at") or time.time()
        elapsed = max(0.1, end_time - job["started_at"])
        status, current = job["status"], job["current"]
        errors = job["errors"]

    eta = None
    avg = elapsed / done if done > 0 else None
    if status == "processing" and avg:
        eta = avg * (total - done) / max(1, WORKERS)

    return {
        "job_id": job["id"],
        "status": status,
        "total": total,
        "done": done,
        "errors": errors,
        "current": current,
        "model": job.get("mode") if job.get("mode") == "cloud" else job.get("model_key", "base"),
        "elapsed_sec": round(elapsed, 1),
        "eta_sec": round(eta, 1) if eta is not None else None,
        "eta_text": fmt_eta(eta) if eta is not None else None,
        "results": results,
    }

@app.get("/", response_class=HTMLResponse)
def index():
    html_file = BASE_DIR / "index.html"
    if not html_file.exists():
        return HTMLResponse("<h2>Error: index.html file not found</h2>", status_code=500)
    return html_file.read_text(encoding="utf-8")

@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    ico_path = BASE_DIR / "favicon.ico"
    if ico_path.exists():
        return FileResponse(ico_path, media_type="image/x-icon")
    return HTMLResponse("", status_code=404)

@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg():
    svg_path = BASE_DIR / "favicon.svg"
    if svg_path.exists():
        return FileResponse(svg_path, media_type="image/svg+xml")
    return HTMLResponse("", status_code=404)

@app.get("/api/health")
def health():
    cli = find_whisper_cli()
    ffmpeg_bin = find_ffmpeg()
    avail_models = get_available_models()
    model_status = {k: (GGML_DIR / v).exists() for k, v in MODELS.items()}
    for k in avail_models:
        model_status[k] = True

    return {
        "ok": cli.exists() and bool(avail_models) and bool(ffmpeg_bin),
        "cli_found": cli.exists(),
        "cli_path": str(cli),
        "ffmpeg_found": bool(ffmpeg_bin),
        "ffmpeg_path": ffmpeg_bin or "Not found",
        "models_dir": str(GGML_DIR),
        "models": model_status,
        "available_models": list(avail_models.keys()),
    }

@app.post("/api/jobs")
async def create_job(
    files: list[UploadFile] = File(...),
    language: str = Form("ur"),
    want_summary: bool = Form(False),
    model: str = Form("base"),
    mode: str = Form("local"),
    api_provider: str = Form("groq"),
    api_key: str = Form(""),
):
    job_model_path = None
    if mode == "local":
        cli = find_whisper_cli()
        if not cli.exists():
            return JSONResponse({"error": f"whisper-cli.exe nahi mila!"}, status_code=400)
        avail_models = get_available_models()
        if not avail_models:
            return JSONResponse({"error": f"Koi model file (.bin) nahi mili!"}, status_code=400)
        model_key = model if model in avail_models else next(iter(avail_models.keys()))
        job_model_path = avail_models[model_key]
    else:
        model_key = f"cloud-{api_provider}"

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, f in enumerate(files):
        suffix = Path(f.filename or "audio.ogg").suffix or ".ogg"
        name = safe_name(f.filename or f"audio_{i}{suffix}")
        dest = job_dir / f"{i:05d}_{name}"
        with open(dest, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                out.write(chunk)
        saved.append({"path": str(dest), "name": name})

    if not saved:
        return JSONResponse({"error": "Koi audio file upload nahi hui."}, status_code=400)

    job = {
        "id": job_id,
        "dir": job_dir,
        "language": language,
        "mode": mode,
        "api_provider": api_provider,
        "api_key": api_key,
        "model_key": model_key,
        "model_path": job_model_path,
        "want_summary": str(want_summary).lower() in ("true", "1", "on", "yes"),
        "files": saved,
        "total": len(saved),
        "done": 0,
        "errors": 0,
        "results": [],
        "current": None,
        "status": "processing",
        "started_at": time.time(),
        "finished_at": None,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    for idx in range(len(saved)):
        TASK_QUEUE.put((job_id, idx))

    return {"job_id": job_id, "total": len(saved)}

@app.post("/api/transcribe")
async def transcribe_endpoint(
    file: UploadFile = File(...),
    language: str = Form("ur"),
    api_provider: str = Form("groq"),
    api_key: str = Form(""),
    want_summary: str = Form("false"),
):
    key = (api_key or "").strip() or os.getenv("GROQ_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not key:
        return JSONResponse(
            {"error": "API Key darj karein! Groq (console.groq.com) ya OpenAI key zaroori hai."},
            status_code=400,
        )

    provider = (api_provider or "groq").lower()
    started = time.time()

    if provider == "openai":
        base_url = "https://api.openai.com/v1/audio/transcriptions"
        model_name = "whisper-1"
    else:
        base_url = "https://api.groq.com/openai/v1/audio/transcriptions"
        model_name = "whisper-large-v3"

    try:
        content = await file.read()
        filename = file.filename or "audio.mp3"
        content_type = file.content_type or "audio/mpeg"

        files = {"file": (filename, content, content_type)}
        data = {
            "model": model_name,
            "response_format": "verbose_json",
        }
        if language and language != "auto":
            data["language"] = language

        headers = {"Authorization": f"Bearer {key}"}

        resp = requests.post(base_url, headers=headers, files=files, data=data, timeout=60)
        
        if resp.status_code != 200:
            err_msg = resp.text
            try:
                err_data = resp.json()
                err_msg = err_data.get("error", {}).get("message", resp.text)
            except Exception:
                pass
            return JSONResponse({"error": f"Cloud API Error ({resp.status_code}): {err_msg}"}, status_code=resp.status_code)

        result_data = resp.json()
        took_sec = round(time.time() - started, 2)
        full_text = result_data.get("text", "").strip()
        duration = result_data.get("duration", 0)

        summary = None
        if str(want_summary).lower() in ("true", "1", "yes") and full_text and provider == "groq":
            try:
                sum_resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {
                                "role": "system",
                                "content": "Neeche ek voice note ka text hai. Iska Roman Urdu mein 1-2 jumlon mein khulasa likhein."
                            },
                            {"role": "user", "content": full_text}
                        ],
                        "max_tokens": 150
                    },
                    timeout=15,
                )
                if sum_resp.status_code == 200:
                    summary = sum_resp.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                summary = None

        return {
            "status": "ok",
            "filename": filename,
            "text": full_text,
            "duration": fmt_time(duration),
            "took_sec": took_sec,
            "language": result_data.get("language") or language,
            "summary": summary,
            "segments": result_data.get("segments", [])
        }
    except Exception as e:
        return JSONResponse({"error": f"Server processing error: {str(e)}"}, status_code=500)

@app.get("/api/jobs")
def list_jobs(limit: int = Query(5, ge=1, le=50)):
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda j: j["started_at"], reverse=True)
        return {"jobs": [{"job_id": j["id"], "status": j["status"]} for j in jobs[:limit]]}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, after: int = Query(0, ge=0)):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return JSONResponse({"error": "Job nahi mili"}, status_code=404)
        snapshot = job_public(job, after=after)

    if snapshot["status"] in ("done", "cancelled"):
        all_path = job["dir"] / "all.txt"
        if not all_path.exists():
            all_path.write_text(build_all_text(job), encoding="utf-8")
        snapshot["download_url"] = f"/api/jobs/{job_id}/download"
    return snapshot

@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return JSONResponse({"error": "Job nahi mili"}, status_code=404)
        if job["status"] == "processing":
            job["status"] = "cancelled"
            job["current"] = None
            job["finished_at"] = time.time()
        return {"job_id": job_id, "status": job["status"]}

@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return JSONResponse({"error": "Job nahi mili"}, status_code=404)
    all_path = job["dir"] / "all.txt"
    return FileResponse(all_path, filename=f"transcripts_{job_id}.txt", media_type="text/plain; charset=utf-8")

if __name__ == "__main__":
    print("=" * 60)
    print("  HYBRID VOICE TO TEXT SERVER (PORTFOLIO EDITION)")
    print("=" * 60)
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT)
