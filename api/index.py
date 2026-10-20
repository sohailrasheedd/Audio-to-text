import os
import time
from pathlib import Path
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Voice to Text API - Vercel Serverless")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def fmt_time(seconds: float) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m:02d}:{s:02d}"

@app.get("/")
def home():
    for p in [Path("public/index.html"), Path("index.html")]:
        if p.exists():
            return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Voice to Text Serverless API Live</h1>")

@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "platform": "vercel",
        "cli_found": False,
        "ffmpeg_found": False,
        "cloud_ready": True,
        "message": "Cloud Vercel Serverless Ready"
    }

@app.post("/transcribe")
@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("ur"),
    api_provider: str = Form("groq"),
    api_key: str = Form(""),
    want_summary: str = Form("false"),
):
    key = (api_key or "").strip() or os.getenv("GROQ_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not key:
        return JSONResponse(
            {"error": "API Key zaroori hai! Groq ya OpenAI key enter karein."},
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
                                "content": "Voice note ka Roman Urdu mein 1-2 jumlon mein khulasa likhein."
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
            "summary": summary
        }
    except Exception as e:
        return JSONResponse({"error": f"Server processing error: {str(e)}"}, status_code=500)
