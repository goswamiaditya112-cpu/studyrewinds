# StudyRewind — Architecture Documentation

## Overview

StudyRewind follows a standard three-tier web architecture: a React frontend, a FastAPI backend, and a PostgreSQL database. The distinguishing aspect is the AI processing pipeline, which runs entirely locally on the user's machine without any paid external API calls.

---

## System Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                              │
│  React 18 + TypeScript (Vite)                                    │
│  Single-page application, port 5173                              │
│  Centralized typed API client (lib/api.ts)                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │ REST/JSON over HTTP
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  APPLICATION LAYER                                               │
│  FastAPI v0.4.0 (Python), Uvicorn ASGI, port 8000               │
│                                                                  │
│  Route Modules:                                                  │
│  ├── auth.py       — registration, login, JWT issuance           │
│  ├── subjects.py   — subject CRUD, ownership enforcement         │
│  ├── playlists.py  — YouTube playlist import                     │
│  ├── transcripts.py — video transcript processing                │
│  ├── documents.py  — PDF upload and processing                   │
│  └── search.py     — semantic search endpoint                    │
│                                                                  │
│  Service Modules:                                                │
│  ├── transcript.py — 3-step YouTube pipeline + Whisper           │
│  ├── embedding.py  — local sentence-transformers model           │
│  ├── vector_storage.py — pgvector persistence                    │
│  └── search.py     — cosine similarity search logic              │
└──────────────────────────────┬───────────────────────────────────┘
                               │ SQLAlchemy 2.0 ORM
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                      │
│  PostgreSQL (via Docker) + pgvector extension                    │
│                                                                  │
│  Tables:                                                         │
│  ├── users                                                       │
│  ├── subjects                                                    │
│  ├── playlists                                                   │
│  ├── videos                                                      │
│  ├── transcript_chunks  (with vector(384) column)               │
│  ├── documents                                                   │
│  └── document_chunks    (with vector(384) column)               │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Ownership Model

StudyRewind enforces strict user data isolation through a hierarchical ownership chain:

```
User
 └── Subject (e.g., "Operating Systems")
      ├── Playlist (e.g., "Gate Smashers OS Playlist")
      │    └── Video (individual YouTube video)
      │         └── TranscriptChunk (60–90 second text window + embedding)
      └── Document (uploaded PDF)
           └── DocumentChunk (page-aware text chunk + embedding)
```

Every API endpoint that accesses user data first validates ownership. A request for a resource that exists but belongs to a different user returns `404 Not Found` — not `403 Forbidden` — to prevent information leakage about resource existence.

---

## Request Flow — Semantic Search

```
POST /api/v1/subjects/{subject_id}/search
{"query": "what is deadlock?", "top_k": 10}

1. JWT verified → current user extracted
2. subject_id ownership validated (404 if not owned)
3. Query text → EmbeddingService → 384-d normalized vector
4. pgvector cosine distance search on transcript_chunks WHERE video.playlist.subject_id = subject_id
5. pgvector cosine distance search on document_chunks WHERE document.subject_id = subject_id
6. Results merged, ranked by score
7. Structured response with provenance metadata
```

---

## Request Flow — Transcript Processing

```
POST /api/v1/videos/{video_id}/transcript/processing

1. JWT verified → current user extracted
2. video_id ownership validated through video → playlist → subject → user chain
3. get_or_process_transcript():
   a. Check if already completed → return cached (idempotent)
   b. Attempt youtube-transcript-api (2 seconds, may be IP-blocked)
   c. Attempt yt-dlp subtitle download (3–5 seconds)
   d. Fallback: yt-dlp audio download → faster-whisper transcription (1–2 min)
4. chunk_transcript() → 60–90 second windows with timestamps
5. Old chunks deleted → new chunks inserted
6. store_chunks_embeddings_batch() → 384-d embeddings → pgvector
7. video.status = "completed"
8. Response returned to frontend
```

---

## Technology Decisions

### Why FastAPI?
FastAPI provides automatic OpenAPI documentation, native async support, Pydantic-based schema validation, and Dependency Injection — all useful for a REST API serving a React frontend. It is significantly faster to develop with than Django REST Framework for this type of project.

### Why PostgreSQL + pgvector instead of a dedicated vector database?
pgvector adds vector similarity search directly to PostgreSQL. This means the project only needs one database system, relational queries and vector searches run in the same transaction context, and the setup is simpler for a college project. A dedicated vector database (like Pinecone or Weaviate) would require managing a second service and adds complexity without significant benefit at this scale.

### Why sentence-transformers locally instead of OpenAI embeddings?
Using a local model means zero API cost, no rate limits, no internet dependency for inference, and full data privacy. The chosen model (`paraphrase-multilingual-MiniLM-L12-v2`) handles both Hindi and English text, which is important for Indian educational content.

### Why faster-whisper locally instead of a cloud ASR service?
Local Whisper processing means transcription works regardless of API availability or cost. The `base` model with `int8` quantization runs on a laptop CPU without a GPU. The tradeoff is speed (~1 minute per 7 minutes of audio on CPU) versus cost (free vs. ~$0.006/min for cloud services).

### Why React + TypeScript?
React with TypeScript provides type safety across the frontend codebase, catching errors at compile time. Vite provides fast development builds. This is a standard, well-documented setup appropriate for a final-year project.

---

## CORS Configuration

The backend allows cross-origin requests from the following origins (local development only):

```python
allow_origins = [
    "http://localhost:5173",   # Vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:3000",   # Alternative dev port
    "http://127.0.0.1:3000",
]
```

---

## API Versioning

All routes are registered with dual prefixes (`/api` and `/api/v1`) for compatibility:

```python
app.include_router(auth_router, prefix="/api")
app.include_router(auth_router, prefix="/api/v1")
```

---

## Deployment Note

The current implementation is designed for local development. Production deployment would require additional work including environment variable management, HTTPS configuration, CORS restriction to a specific domain, and a persistent database volume.
