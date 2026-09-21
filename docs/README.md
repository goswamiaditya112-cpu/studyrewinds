# StudyRewind

**An AI-powered educational study assistant that turns YouTube playlists and PDF notes into a searchable knowledge base.**

StudyRewind is a full-stack web application that ingests YouTube lecture playlists and PDF study materials, transcribes and processes them locally using AI, and provides semantic search so students can find exactly what they are looking for — with timestamps and page references.

All AI processing runs locally. No paid APIs. No cloud AI services. No data sent to external servers.

---

## Table of Contents

- [What Problem Does It Solve?](#what-problem-does-it-solve)
- [Features](#features)
- [How It Works](#how-it-works)
- [Technology Stack](#technology-stack)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Setup and Installation](#setup-and-installation)
- [How to Run](#how-to-run)
- [Running Tests](#running-tests)
- [Known Limitations](#known-limitations)
- [Screenshots](#screenshots)
- [License](#license)

---

## What Problem Does It Solve?

Students watching hours of lecture videos on YouTube face a common problem: finding a specific concept later requires scrubbing through entire videos. Similarly, PDF notes are hard to search when you only remember a vague idea, not the exact keywords.

StudyRewind solves this by:

1. Extracting transcripts from YouTube lecture videos and text from PDF notes
2. Converting both into semantic vector representations (embeddings)
3. Storing them in a vector database (PostgreSQL + pgvector)
4. Allowing students to search using natural language — finding results even when they don't remember exact words

---

## Features

### Study Material Management
- Create academic subjects (e.g., "Operating Systems", "DBMS")
- Import any public YouTube playlist by URL
- Upload PDF study notes and textbook chapters

### YouTube Transcript Extraction — Three-Step Pipeline
- **Step 1:** Reads YouTube's free auto-generated captions (fast, ~2 seconds)
- **Step 2:** Downloads subtitle files via yt-dlp when captions are IP-blocked (~3–5 seconds)
- **Step 3:** Local Whisper AI fallback — downloads audio and transcribes locally (~1–2 minutes per video)
- Supports Hindi and English transcripts
- Preserves original timestamps for every chunk

### PDF Processing
- Extracts text from uploaded PDF files page by page using pypdf
- Chunks extracted text and generates embeddings
- Preserves page number provenance for every result

### Semantic Search
- Natural language queries across all study materials in a subject
- Returns relevant transcript or PDF chunks with:
  - YouTube timestamp (click to jump to the right moment in the video)
  - PDF page number reference
- Multilingual: supports Hindi and English queries and content

### User Accounts and Data Isolation
- Full user registration and login system
- JWT-based authentication
- Strict ownership isolation — users can only access their own data
- IDOR protection at every API endpoint

---

## How It Works

```
Student enters query: "what is deadlock?"
        │
        ▼
Query is converted to a 384-dimensional vector
(sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)
        │
        ▼
PostgreSQL + pgvector searches stored transcript and document chunks
using cosine similarity
        │
        ▼
Top matching chunks returned with provenance:
  • YouTube: video title + timestamp → click to open at exact moment
  • PDF: document name + page number
```

---

## Technology Stack

### Backend
| Component | Technology | Version |
|---|---|---|
| Web framework | FastAPI | ≥0.110.0 |
| ASGI server | Uvicorn | ≥0.28.0 |
| ORM | SQLAlchemy | ≥2.0.28 |
| Database migrations | Alembic | ≥1.13.1 |
| Database driver | psycopg (v3) | ≥3.1.18 |
| Password hashing | argon2-cffi (Argon2id) | ≥23.1.0 |
| Authentication tokens | PyJWT | ≥2.8.0 |
| Settings management | pydantic-settings | ≥2.2.1 |

### AI / ML
| Component | Technology | Version |
|---|---|---|
| Local embeddings | sentence-transformers | ≥3.0.0 |
| Embedding model | paraphrase-multilingual-MiniLM-L12-v2 | — |
| Vector database | pgvector (PostgreSQL extension) | ≥0.2.5 |
| Speech transcription | faster-whisper | ≥1.0.0 |
| Whisper model | base (int8 quantized) | — |
| YouTube audio download | yt-dlp | ≥2026.8.0 |
| YouTube captions | youtube-transcript-api | ≥1.2.0 |
| PDF text extraction | pypdf | ≥4.0.0 |

### Frontend
| Component | Technology |
|---|---|
| Framework | React 18 + TypeScript |
| Build tool | Vite |
| Styling | CSS (custom, no UI framework) |
| HTTP client | Fetch API (typed, centralized) |

### Database
| Component | Technology |
|---|---|
| Primary database | PostgreSQL |
| Vector search extension | pgvector |
| Local development | Docker (postgres container) |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    React + TypeScript Frontend                   │
│                    (Vite, port 5173)                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / REST (JSON)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (port 8000)                   │
│                                                                 │
│  /api/v1/auth           — register, login, me                   │
│  /api/v1/subjects       — CRUD for academic subjects            │
│  /api/v1/playlists      — YouTube playlist import               │
│  /api/v1/videos         — video transcript processing           │
│  /api/v1/documents      — PDF upload and processing             │
│  /api/v1/subjects/{id}/search — semantic search                 │
└──────────┬────────────────────────────┬────────────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────────┐    ┌────────────────────────────────────┐
│   PostgreSQL + pgvector│    │     Local AI Services              │
│                      │    │                                    │
│  users               │    │  faster-whisper (base, int8, CPU)  │
│  subjects            │    │  paraphrase-multilingual-MiniLM    │
│  playlists           │    │  yt-dlp (audio + subtitle)         │
│  videos              │    │  youtube-transcript-api            │
│  transcript_chunks   │    │  pypdf                             │
│  documents           │    │                                    │
│  document_chunks     │    └────────────────────────────────────┘
└──────────────────────┘
```

---

## Project Structure

```
studyrewinds/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   │   ├── auth.py
│   │   │   ├── subjects.py
│   │   │   ├── playlists.py
│   │   │   ├── transcripts.py
│   │   │   ├── documents.py
│   │   │   └── search.py
│   │   ├── core/             # Config, security utilities
│   │   │   ├── config.py
│   │   │   └── security.py   # Argon2id hashing, JWT
│   │   ├── db/               # Database session, base
│   │   ├── models/           # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── subject.py
│   │   │   ├── playlist.py
│   │   │   ├── video.py
│   │   │   ├── document.py
│   │   │   └── chunk.py      # TranscriptChunk + DocumentChunk
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic
│   │   │   ├── transcript.py # 3-step YouTube pipeline
│   │   │   ├── embedding.py  # Local embedding generation
│   │   │   ├── vector_storage.py  # pgvector persistence
│   │   │   └── search.py     # Semantic search logic
│   │   └── main.py           # FastAPI app + CORS + router registration
│   ├── tests/                # 15 test files (pytest)
│   ├── alembic/              # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Main application component
│   │   └── lib/
│   │       └── api.ts        # Typed API client
│   ├── package.json
│   └── vite.config.ts
└── docs/                     # Phase 14 documentation
```

---

## Setup and Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | For the backend |
| Node.js 18+ | For the frontend |
| Docker Desktop | For PostgreSQL container |
| FFmpeg | For audio format conversion (recommended) |
| Git | To clone the repository |

### 1. Clone the Repository

```bash
git clone <repository-url>
cd studyrewinds
```

### 2. Start PostgreSQL with pgvector

```bash
docker start backend-postgres-1
```

If the container does not exist yet, create it:

```bash
docker run --name backend-postgres-1 \
  -e POSTGRES_USER=studyrewind \
  -e POSTGRES_PASSWORD=change-me \
  -e POSTGRES_DB=studyrewinds_dev \
  -p 5432:5432 \
  -d pgvector/pgvector:pg16
```

### 3. Set Up Backend

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Create .env file
copy backend\.env.example backend\.env
# Edit backend\.env and set DATABASE_URL and JWT_SECRET_KEY

# Run database migrations
set PYTHONPATH=backend
alembic -c backend/alembic.ini upgrade head
```

### 4. Set Up Frontend

```bash
cd frontend
npm install
cd ..
```

---

## How to Run

### Start Backend

```bash
# From project root
set PYTHONPATH=backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

The backend API is now available at `http://localhost:8000`

API documentation (Swagger UI): `http://localhost:8000/docs`

### Start Frontend

```bash
# From project root
cd frontend
npm run dev
```

The frontend is now available at `http://localhost:5173`

### Health Check

Visit `http://localhost:8000/health` — should return `{"status": "ok"}`

Visit `http://localhost:8000/health/db` — should confirm PostgreSQL and pgvector are reachable.

---

## Running Tests

```bash
# From project root
set PYTHONPATH=backend
.\venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected result: **184 tests, 0 failures**

Test coverage includes:
- Authentication (register, login, token validation)
- Subject management (CRUD + ownership)
- Playlist import and video processing
- Transcript extraction and chunking
- PDF upload and processing
- Embedding generation and validation
- pgvector storage and retrieval
- Semantic search API
- Security hardening (IDOR prevention, authorization boundary tests)
- Database schema integrity

---

## Known Limitations

| Limitation | Details |
|---|---|
| **YouTube IP blocking** | YouTube may block caption/subtitle requests from networks that make many automated requests. Whisper fallback handles this automatically. |
| **Whisper speed on CPU** | Transcription on CPU takes approximately 1 minute per 7 minutes of video. A dedicated GPU would be significantly faster. |
| **Synchronous processing** | Transcript processing is synchronous — the browser waits until processing completes. Large playlists processed one video at a time. |
| **Private/age-restricted videos** | Only public YouTube videos are supported. |
| **English and Hindi focus** | The embedding model and preferred language detection focus on English and Hindi. Other languages will still process but with less tuning. |
| **Local-only deployment** | The current setup is designed for localhost development. Production deployment requires additional configuration. |
| **No real-time updates** | The UI does not automatically refresh transcript status — manual refresh required. |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register new user |
| `POST` | `/api/v1/auth/login` | Login, receive JWT |
| `GET` | `/api/v1/auth/me` | Get current user |
| `GET/POST` | `/api/v1/subjects` | List / create subjects |
| `GET/PUT/DELETE` | `/api/v1/subjects/{id}` | Get / update / delete subject |
| `GET/POST` | `/api/v1/playlists` | List / import playlist |
| `GET/DELETE` | `/api/v1/playlists/{id}` | Get / delete playlist |
| `GET` | `/api/v1/playlists/{id}/videos` | List videos in playlist |
| `POST` | `/api/v1/videos/{id}/transcript/processing` | Process single video transcript |
| `GET` | `/api/v1/videos/{id}/transcript` | Get transcript chunks |
| `POST` | `/api/v1/documents` | Upload PDF |
| `GET` | `/api/v1/documents/{id}` | Get document info |
| `POST` | `/api/v1/subjects/{id}/search` | Semantic search |
| `GET` | `/health` | Backend health |
| `GET` | `/health/db` | Database + pgvector health |

---

## License

This is a college final-year project developed for educational purposes.
