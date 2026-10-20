"""Whisper model download helper - resumable, xet off.

Usage: python download_model.py base|small|medium|large-v3
"""
import os
import sys

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from faster_whisper import WhisperModel  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else "medium"
print(f"Downloading {name} ...", flush=True)
WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=2)
print(f"MODEL {name} READY", flush=True)
