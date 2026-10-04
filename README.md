# 🎓 StudyRewind

> **An AI-powered semantic search engine for college students that turns long YouTube lecture playlists and PDF notes into an instant, searchable knowledge base.**

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React_18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-Cosine_Search-blue?style=for-the-badge)](https://github.com/pgvector/pgvector)
[![Tests](https://img.shields.io/badge/Tests-184%20Passed-success?style=for-the-badge&logo=pytest)](https://docs.pytest.org/)

---

## 📺 Live Demo Video

Watch StudyRewind extract transcripts, process PDFs, and execute semantic vector search with exact timestamps:

[![StudyRewind Demo Video](https://img.youtube.com/vi/5xIW6lkczRc/maxresdefault.jpg)](https://youtu.be/5xIW6lkczRc)

> **[▶ Click here to watch the full demo on YouTube](https://youtu.be/5xIW6lkczRc)**

---

## 💡 The Problem & The Solution

| The Student Problem | StudyRewind Engineering Solution |
| :--- | :--- |
| **Hours spent scrubbing videos:** College lectures on YouTube (Gate Smashers, NPTEL) span 50–100+ videos. Finding one specific formula or explanation is painfully slow. | **Temporal Chunking & Jump Links:** Transcripts are chunked into 60–90s windows. Search returns a direct link opening YouTube at that exact second. |
| **Keyword search (Ctrl+F) fails:** If a student searches _"avoiding starvation"_, keyword search misses lectures where the professor said _"aging priority"_. | **Dense Multilingual Vector Search:** Uses `sentence-transformers` (384 dimensions) to match by conceptual meaning across English, Hindi, and Hinglish. |
| **Fragmented study sources:** Lecture videos are on YouTube, while textbook notes are scattered in PDFs. | **Multimodal Ingestion:** Indexes both YouTube audio and PDF pages into a unified PostgreSQL vector store. |
| **Expensive cloud AI APIs:** Modern AI tools charge recurring subscription fees and risk hallucinating fake answers. | **100% Free, Local & Grounded:** Runs entirely on CPU with zero cloud costs. Delivers exact source citations rather than generated hallucinations. |

---

## 🏗️ System Architecture

```
STUDYREWIND ARCHITECTURE

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          React 18 + TypeScript SPA                                     │
│              (Course Workspaces • Video Player • Semantic Search UI)                   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │  REST API / JWT Bearer
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI Backend (Python)                                  │
│            (Argon2id Auth • Ingestion Services • Chunking Engines • IDOR Security)    │
└──────────────┬────────────────────────────┬─────────────────────────────┬──────────────┘
               │                            │                             │
               ▼                            ▼                             ▼
  [ YouTube Ingestion ]          [ Local AI Models ]          [ Relational Vector DB ]
  • youtube-transcript-api       • faster-whisper (int8 ASR)  • PostgreSQL 16 + pgvector
  • yt-dlp (VTT Subtitles)       • paraphrase-multilingual    • HNSW Graph Cosine Index
  • DASH m4a audio stream          MiniLM-L12-v2 (384-d)      • Cascade Deletion Integrity
```

---

## ⚡ Engineering Highlights

### 1. Robust 3-Tier Transcription Fallback

YouTube aggressively rate-limits automated requests. To ensure high availability without paid APIs, StudyRewind implements an automated fallback hierarchy:

1. **Tier 1 (YouTube Captions):** Scrapes official public captions via `youtube-transcript-api` (~2s).
2. **Tier 2 (yt-dlp Subtitle Scraping):** If Tier 1 is rate-limited, downloads browser-impersonated `.vtt` subtitles (~3–5s) with a custom parser that deduplicates rolling-window captions.
3. **Tier 3 (Local Whisper ASR):** If no captions exist, downloads the audio track and runs quantized `faster-whisper` locally on CPU (~1 min per 7-min video) with thread capping to prevent laptop thermal throttling.

### 2. Page-Aware PDF Extraction

Uses `pypdf` to extract text page-by-page. Text chunks strictly snap to physical page boundaries, guaranteeing that search citations point to the 100% accurate textbook page.

### 3. PostgreSQL + pgvector

Eliminates the operational overhead of a separate vector database (like Pinecone). Relational user ownership and vector similarity search (`ORDER BY embedding <=> query_vector`) are computed inside a single atomic query.

### 4. Rigorous Security & Testing

- Passwords hashed using **Argon2id** (RFC 9106 recommended).
- Full IDOR prevention across all endpoints (unauthorized resource access returns `404 Not Found`).
- **184 automated tests** passing covering auth, ingestion, embeddings, and security boundaries.

---

## 🛠️ Tech Stack Breakdown

- **Frontend:** React 18, TypeScript, Vite, Custom CSS design tokens
- **Backend:** FastAPI, Python 3.11+, Pydantic v2, Uvicorn
- **Database & Vectors:** PostgreSQL 16, pgvector, SQLAlchemy 2.0, Alembic
- **Machine Learning & NLP:**
  - `faster-whisper` (OpenAI Whisper base model, int8 quantization, CPU inference)
  - `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions)
- **Ingestion & Parsing:** `yt-dlp`, `youtube-transcript-api`, `pypdf`
- **Authentication & Security:** Argon2id (`argon2-cffi`), PyJWT
- **Testing:** Pytest, HTTPX, FastAPI TestClient

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- Docker Desktop

### 2. Start PostgreSQL with pgvector

```bash
docker run --name backend-postgres-1 \
  -e POSTGRES_USER=studyrewind \
  -e POSTGRES_PASSWORD=change-me \
  -e POSTGRES_DB=studyrewinds_dev \
  -p 5432:5432 \
  -d pgvector/pgvector:pg16
```

### 3. Start Backend

```bash
# In project root
python -m venv venv
.\venv\Scripts\activate
pip install -r backend/requirements.txt

# Run migrations
$env:PYTHONPATH="backend"
alembic -c backend/alembic.ini upgrade head

# Launch server
$env:PYTHONPATH="backend"
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

### 4. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Automated Testing

Execute the complete 184-test verification suite:

```bash
$env:PYTHONPATH="backend"
pytest backend/tests -q
```

```
============================== 184 passed in 105.4s ==============================
```

---

## 📋 Core API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | `/api/v1/auth/register` | Secure registration with Argon2id password hashing |
| POST | `/api/v1/auth/login` | Issues stateless JWT Bearer token |
| POST | `/api/v1/playlists` | Ingests YouTube playlist and catalogues all video metadata |
| POST | `/api/v1/videos/{id}/transcript/processing` | Triggers 3-tier transcript extraction pipeline |
| POST | `/api/v1/study-materials` | Uploads PDF notes and extracts page-aware chunks |
| POST | `/api/v1/subjects/{id}/search` | Multimodal semantic search returning video timestamps & PDF pages |

---

## 👤 Author

Developed by **Aditya Goswami**
