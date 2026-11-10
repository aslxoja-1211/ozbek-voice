# Aqua Voice Uzbek — O'zbek Tili Uchun AI Ovozli Matn Muharriri

O'zbek tilida jonli gapirib matn kiritish va nutq orqali kontekstual tahrirlash (`APPEND`, `REPLACE`, `DELETE`, `FORMAT`) imkonini beruvchi aqlli ovozli matn muharriri MVP loyihasi.

## Arxitektura

```text
[Brauzer Mikrofoni (Web Audio API 16kHz PCM)]
                   │
        WebSocket (/ws/voice, binary + JSON)
                   ▼
     [FastAPI Backend (Python 3.11+)]
       ├── Audio Utils (PCM16 -> WAV, RMS)
       ├── STT Adapter (Mohirpool STT | OpenAI Whisper | Mock)
       ├── LLM Intent Engine (Gemini Flash | GPT-4o-mini | Lokal Rule Fallback)
       └── Text Diff Engine (O'zbek apostrof normalizatsiyasi: o', o‘, oʻ)
                   │
        JSON Diff + Latency Metrics
                   ▼
[Next.js + Tiptap Rich Text Editor]  va  [FastAPI Tezkor Demo UI (/)]
```

## Loyiha Tuzilmasi

- `backend/` — FastAPI server, WebSocket oqim protokoli, STT/LLM adapterlari, Uzbek Text Diff Engine, `static/demo.html` tezkor test sahifasi va `pytest` testlari.
- `frontend/` — Next.js (App Router, TypeScript), Tailwind CSS, Tiptap Rich Text Editor va Web Audio API (`16kHz PCM16`) mijoz ilovasi.
- `.env.example` — API kalitlari va provayder sozlamalari shabloni.

## LLM Chiqish Sxemasi (Qat'iy JSON)

```json
{
  "action": "APPEND | REPLACE | DELETE | FORMAT",
  "target": "o'zgartirilishi kerak bo'lgan matn yoki qism",
  "replacement": "yangi matn",
  "updated_full_text": "ixtiyoriy: agar diff murakkab bo'lsa to'liq matn",
  "confidence": 0.95
}
```

## Tezkor Ishga Tushirish

### 1. Konfiguratsiya (ixtiyoriy — kalitsiz ham Mock/Demo rejimida ishlaydi)

```powershell
copy .env.example .env
```

`.env` faylida kerakli kalitlarni kiriting (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `MOHIRPOOL_API_KEY`). Agar kalitlar bo'sh qoldirilsa, `STT_PROVIDER=auto` va `LLM_PROVIDER=auto` avtomatik ravishda `mock` (Demo + lokal o'zbekcha buyruq tahlilchisi) rejimida ishlaydi.

### 2. Backend va Tezkor Brauzer Demo UI (Python)

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ishga tushgach:
- Tezkor ovozli muharrir demo sahifasi: `http://localhost:8000/`
- Swagger API hujjatlari: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 3. Backend Testlarini Ishga Tushirish

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -v
```

### 4. Next.js + Tiptap Frontend (Node.js 20+ talab etiladi)

```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

So'ngra `http://localhost:3000` manzilini oching.

## Qo'llab-quvvatlanadigan O'zbekcha Buyruqlar (Misollar)

- **APPEND:** `"Bugun Toshkentda konferensiya bo'lib o'tadi."`
- **REPLACE:** `"kecha so'zini bugun deb o'zgartir"`, `"Toshkentni Samarqandga almashtir"`
- **DELETE:** `"oxirgi gapni o'chir"`, `"oxirgi so'zni o'chir"`, `"hammasini o'chir"`
- **FORMAT:** `"oxirgi gapni ro'yxatga aylantir"`, `"yangi xatboshi"`, `"sarlavha qil"`, `"qalin qil"`, `"nuqta qo'y"`
