# Voice to Text (Urdu focused, local)

WhatsApp voice notes aur dusri audio files ko text mein badalne ka local tool.
Engine: **whisper.cpp** (open source Whisper) — khaas taur par bina AVX wale purane
CPUs (jaise Intel Pentium N4200) par bhi chalta hai. Sab kuch aap ke computer par
hi process hota hai, internet ki zaroorat nahi.

## Chalana

```
start.bat
```

ya manually:

```
venv\Scripts\python.exe app.py
```

Phir browser mein kholein: http://localhost:8000

Zaroori cheezein is folder mein pehle se hain:
- `whisper_bin\whisper-cli.exe` — transcribe karne wala program
- `models\ggml-base.bin` — whisper ka model
- `venv\` — Python environment

## 500+ files ka batch

Sab files ek saath drag karein ya chunein - queue mein lagti hain aur background
mein process hoti rehti hain. Progress bar, baqi waqt (ETA) aur har file ka text
live neeche aata rehta hai. Page refresh bhi kar sakte hain, job waapis lag jati
hai (aur koi aur tab bhi chal rahi hui job dekh sakta hai). Mukammal hone par
"Sab text download karein" se combined .txt milti hai (aur
`transcripts\jobs\<job-id>\all.txt` mein bhi mehfooz rehti hai).

## Raftaar ka haqeeqi andaaza (aham)

Is CPU (Pentium N4200, 4 cores, koi AVX nahi) par har chhoti clip (8-12 sec)
takreeban **1.5 - 3 minute** leti hai. Is ka matlab:

- 10 files  ≈ 20-30 min
- 100 files ≈ 3-5 ghante
- 500 files ≈ 15-24 ghante (jab tak computer chalta rahe, queue chalti rehti hai)

Awaaz lambi ho (misal 1 min voice note) to us ke hisaab se waqt barhta hai.
Progress bar ETA batata rehta hai — batch chalte hue band kar dein to baad mein
dobara khol kar wahi job dobara shuru kar sakte hain.

## Model chunna (page par dropdown)

Page par **Model** dropdown se har job ke liye model chuna ja sakta hai:

| Model | Raftaar | Quality |
|---|---|---|
| **Tez (base)** | ~1.5-3 min/file | Theek - chhoti ghaltiyan (misal "کل" -> "قل") |
| **Behtar (small)** | ~3-5 min/file | Achha - base se behtar, beech ka raasta |
| **Sab se behtareen (medium)** | ~15-25 min/file | Bohat behtar - poora jumla samajh aata hai |

**Mashwara:** 500 files wali batch ke liye `base` hi rakhein. Ahem single voice
note (jise theek se samajhna ho) ke liye `small` ya `medium` chunein.

Env se default badalna ho: `set GGML_MODEL=ggml-medium-q5_0.bin`

## Settings (optional)

```
set WHISPER_THREADS=4                 (har file kitni threads le)
set WHISPER_WORKERS=1                 (ek saath kitni files - zyada workers is CPU par slow)
set PORT=8000
```

Model `models\` folder mein hona chahiye. `medium` model ki quality bohat achi hai
(perfect Urdu) magar is CPU par 8 guna slow hai — single files ke liye kabhi kabhi
istemal kar sakte hain, 500 files ke liye nahi. Default `base` hi rakhein.

## Khulasa (summary) ka option

1. Ollama install karein (ollama.com) aur model le aayen: `ollama pull qwen2.5:7b`
2. Ollama chalta rehne dein, phir page par "Khulasa bhi banayein" tick karein.

Doosra model chahiye to: `set OLLAMA_MODEL=model-ka-naam`

## Aham baat

Whisper Urdu mein achha hai magar 100 percent perfect nahi. `base` model chhoti
ghaltiyan kar sakta hai (misal: "سات بجے" ki jagah "ساتھ بچے"). Agar text samajh
nahi aa raha to **medium** model chunein - woh bohat behtar likhta hai (bas slow
hai). Shor wali ya bohat tez awaaz mein, ya jab Urdu mein English/Punjabi alfaaz
mix hon, to ghalti ho sakti hai. Zaroori messages (paisay, tareekh, address) ek
dafa khud sun kar confirm kar lein.

## Test files

- `test_audio\` — 3 Urdu + 1 English chhoti clips (gTTS se bani)
- `test_batch500\` — 500 copies (stress test ke liye)
- `stress_test.py` — 500 files ek saath bhej kar queue/progress verify karne wala script:
  `venv\Scripts\python.exe stress_test.py`
- `test_single.py` — ek file ka test: `venv\Scripts\python.exe test_single.py [file]`
