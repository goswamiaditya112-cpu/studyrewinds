# StudyRewind — Final Project Report

---

## Title

**StudyRewind: A Local AI-Powered Semantic Search System for Educational Content**

---

## Abstract

StudyRewind is a full-stack web application designed to solve the problem of searching through large collections of YouTube lecture videos and PDF study materials. Students studying from popular Indian engineering education channels face the challenge of finding specific concepts across hundreds of lecture hours. StudyRewind addresses this by automatically extracting transcripts from YouTube videos through a three-step fallback pipeline, extracting text from uploaded PDFs, converting all content into semantic vector representations using a locally-hosted multilingual model, storing these vectors in PostgreSQL with the pgvector extension, and enabling natural language search that returns results with video timestamps and PDF page numbers as provenance.

The system runs entirely on a student's laptop without any paid API services. All AI inference — speech transcription and text embedding — is performed locally. The project was developed across 13 implementation phases covering foundation, authentication, content ingestion, AI pipeline, vector storage, semantic search, frontend, integration, testing, and security hardening.

---

## 1. Introduction

The popularity of YouTube as an educational platform in India has created a new study challenge: students now have access to thousands of hours of lecture content, but no effective way to navigate it beyond linear playback. When revising for exams, a student may remember a concept was explained somewhere in a 20-hour playlist but cannot recall which video or at what time. Similarly, PDFs and textbooks are difficult to search when the reader only remembers the meaning of what they are looking for, not the exact keywords.

StudyRewind proposes a solution based on semantic search — searching by meaning rather than exact keywords. It ingests YouTube playlists and PDFs, processes their content using local AI, and stores semantic vector representations in a PostgreSQL vector database. Students can then query this knowledge base in natural language.

---

## 2. Problem Statement

Engineering students using YouTube for self-study face two problems:

1. **Navigation problem:** Thousands of hours of lecture content with no semantic search capability. YouTube's own search operates only at the video level, not within video content.

2. **Integration problem:** Study material is split across YouTube playlists and PDF notes. There is no unified search across both content types.

**Current workarounds and their limitations:**
- Manual notes: Time-consuming and incomplete
- YouTube chapter markers: Not available on most lecture channels
- Browser CTRL+F: Only works on visible page text, not video transcripts
- YouTube auto-captions search: Not available; captions are only viewable inline

---

## 3. Objectives

1. Build a system that extracts and stores timestamped transcripts from any public YouTube playlist
2. Process uploaded PDF study notes page by page and make them searchable
3. Implement semantic search using local AI embeddings that works across both content types
4. Ensure each search result contains provenance: which video + timestamp, or which PDF + page number
5. Implement secure user accounts with full data isolation
6. Achieve all of the above without paid API services, running on a standard student laptop

---

## 4. Existing Problems and Proposed Solution

| Existing Problem | StudyRewind Solution |
|---|---|
| No semantic search in YouTube | Extract transcripts, embed chunks, provide cosine similarity search |
| Transcript extraction blocked by YouTube | Three-step fallback: captions → subtitles → local Whisper |
| No unified search across video and PDF | Both content types embedded and searched through the same interface |
| Cloud AI costs money | All AI runs locally (faster-whisper, sentence-transformers) |
| No timestamp provenance in existing tools | Every transcript chunk stores start_time and end_time |
| No page number provenance | Every document chunk stores page_number |

---

## 5. System Architecture

StudyRewind uses a three-tier architecture:

**Presentation Layer:** React 18 with TypeScript, built with Vite. Single-page application served on port 5173 during development. Communicates with the backend through a centralized typed API client.

**Application Layer:** FastAPI (Python) backend served by Uvicorn on port 8000. Organized into route modules (auth, subjects, playlists, transcripts, documents, search) and service modules (transcript extraction, embedding generation, vector storage, search). Dual API prefix routing (`/api` and `/api/v1`).

**Data Layer:** PostgreSQL 16 with the pgvector extension, running in Docker. Seven tables storing users, subjects, playlists, videos, transcript chunks, documents, and document chunks. All resource tables linked through cascade-delete foreign keys enforcing referential integrity.

---

## 6. Features

### User Management
- Account registration with email and Argon2id-hashed password
- JWT-based authentication with configurable token expiry
- Full user data isolation — users cannot access each other's data

### Subject Organization
- Create named academic subjects (e.g., "Operating Systems", "DBMS")
- Each subject contains playlists and/or PDF documents
- Semantic search is scoped to a single subject

### YouTube Playlist Ingestion
- Import any public YouTube playlist by URL
- Automatic discovery of all videos in the playlist with titles and durations

### Transcript Extraction (Three-Step Pipeline)
- **Step 1:** `youtube-transcript-api` reads YouTube's free caption files (~2 seconds)
- **Step 2:** yt-dlp downloads the subtitle text file, bypassing IP-based rate limiting (~3–5 seconds)
- **Step 3:** faster-whisper transcribes locally from downloaded audio (~1 min per 7 min of video)
- Hindi and English supported; language auto-detected
- Timestamps preserved for every 60–90 second chunk

### PDF Processing
- Upload PDF files through the web interface
- pypdf extracts text page by page
- Page number preserved for every chunk

### Local Embedding Generation
- Model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Output: 384-dimensional normalized unit vectors
- Supports English and Hindi content
- Batch processing with idempotency (skips already-embedded chunks)

### Semantic Search
- POST `/api/v1/subjects/{id}/search` with a natural language query
- Query converted to 384-d vector locally
- pgvector cosine distance search across transcript and document chunks
- Results include video timestamp or PDF page number

---

## 7. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite |
| Backend | FastAPI 0.110+, Python, Uvicorn |
| ORM | SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16, pgvector |
| DB Driver | psycopg v3 |
| Auth | Argon2id (argon2-cffi), PyJWT |
| Validation | Pydantic v2, pydantic-settings |
| Speech AI | faster-whisper (base, int8, CPU) |
| Embedding AI | sentence-transformers (MiniLM-L12-v2) |
| YouTube | yt-dlp, youtube-transcript-api |
| PDF | pypdf |
| Testing | pytest, httpx |

---

## 8. Database Design

Seven tables implement the data model:

- `users` — accounts with Argon2id password hashes
- `subjects` — academic course groupings owned by users
- `playlists` — imported YouTube playlists linked to subjects
- `videos` — individual videos with transcript status tracking
- `transcript_chunks` — 60–90s text windows with `vector(384)` embedding
- `documents` — uploaded PDF files linked to subjects
- `document_chunks` — page-aware text chunks with `vector(384)` embedding

All foreign keys cascade on delete. All primary keys are UUIDs.

---

## 9. YouTube Transcript Pipeline

```
POST /api/v1/videos/{video_id}/transcript/processing
        │
        ├── Ownership verified
        │
        ├── Step 1: youtube-transcript-api
        │          Hindi preferred, English fallback
        │          ~2 seconds on success
        │          Fails if IP is rate-limited
        │
        ├── Step 2: yt-dlp subtitle download
        │          Downloads .vtt text file only (30–100 KB)
        │          ~3–5 seconds on success
        │          Works even when Step 1 is rate-limited
        │
        ├── Step 3: faster-whisper
        │          yt-dlp downloads audio (.m4a, 10–18 MB)
        │          faster-whisper transcribes on CPU
        │          ~1 min per 7 min of audio
        │          Always works; no YouTube contact needed
        │
        ├── chunk_transcript() — 60–90s windows
        │
        ├── Store TranscriptChunk records
        │
        ├── store_chunks_embeddings_batch() — 384-d vectors
        │
        └── video.status = "completed"
```

---

## 10. PDF Pipeline

```
POST /api/v1/documents (multipart upload)
        │
        ├── File saved to disk
        ├── Document record created (status: processing)
        │
        ├── pypdf extracts text per page
        ├── Each page chunked if needed
        ├── DocumentChunk records created with page_number
        │
        ├── store_chunks_embeddings_batch() — 384-d vectors
        │
        └── document.status = "completed"
```

---

## 11. AI and Embedding Pipeline

All AI inference runs on the local CPU:

**Embedding model:** `paraphrase-multilingual-MiniLM-L12-v2`
- Loaded once at startup, cached in memory
- Processes text in batches of 32
- Outputs 384-dimensional L2-normalized vectors
- Validated for correct dimension and finite values

**Vector storage:** pgvector `vector(384)` columns in `transcript_chunks` and `document_chunks`. Idempotency check prevents re-embedding already-embedded chunks. Batch commit with rollback on failure.

**Search:** Query text → `embed_text()` → 384-d vector → pgvector `<=>` cosine distance operator → top-K results ordered by ascending distance.

---

## 12. Security Implementation

| Security Control | Implementation |
|---|---|
| Password storage | Argon2id (argon2-cffi), PHC string format |
| Authentication | PyJWT signed tokens, `sub` = user UUID |
| Authorization | Ownership check at every endpoint |
| IDOR prevention | UUID primary keys + 404 for unauthorized access |
| SQL injection | SQLAlchemy ORM with parameterized queries |
| Input validation | Pydantic schemas on all request bodies |
| CORS | Restricted to localhost:5173 and localhost:3000 |

---

## 13. Testing

The test suite contains 184 tests across 13 test files:

| Test Module | Focus |
|---|---|
| `test_auth.py` | Registration, login, token validation |
| `test_subjects.py` | CRUD, ownership isolation |
| `test_playlists.py` | Import, video discovery, ownership |
| `test_transcripts.py` | Transcript processing, chunking, cleanup |
| `test_documents.py` | PDF upload, processing |
| `test_embedding.py` | Embedding generation, validation, batching |
| `test_vector_storage.py` | pgvector storage, idempotency |
| `test_search.py` | Semantic search, scoping, ranking |
| `test_phase12_security_hardening.py` | IDOR prevention, cross-user isolation |
| Others | Schema, pgvector, health checks |

**Baseline:** 184 passed, 0 failed (run time ~105 seconds).

---

## 14. Results

The system was validated end-to-end with real YouTube lecture content:

- Three Hindi OS lecture videos (Gate Smashers channel) transcribed successfully using faster-whisper
- Transcript sources: `whisper` (IP-blocked network), correctly falls back
- Average: 10–18 transcript chunks per video with accurate timestamps
- All chunks embedded (384-d vectors stored in pgvector)
- Duplicate processing prevention verified: second retrieval returns existing chunks in <1 second
- Temporary audio cleanup: 0 leaked directories across 5 test runs
- All 184 automated tests passing

---

## 15. Known Limitations

1. **YouTube rate limiting:** YouTube may IP-block caption and subtitle requests, requiring the slower Whisper fallback
2. **CPU-only inference:** Whisper transcription on CPU averages ~1 minute per 7 minutes of audio
3. **Synchronous processing:** Browser waits for each video to complete; no background queue
4. **Public videos only:** Private, age-restricted, or deleted YouTube videos cannot be processed
5. **Local deployment:** Not configured for production internet hosting
6. **No generative AI:** System retrieves content but does not generate answers

---

## 16. Future Possibilities

1. **Async task queue:** Celery + Redis for background transcript processing
2. **Generative layer:** LLM integration for question answering using retrieved chunks as context
3. **GPU acceleration:** Whisper inference on GPU for 10–20x speed improvement
4. **More content types:** Support for local audio/video files, other video platforms
5. **Production deployment:** HTTPS, proper authentication cookies, cloud database
6. **Multilingual expansion:** Expanded language detection and support

---

## 17. Conclusion

StudyRewind demonstrates that a practical AI-powered study tool can be built entirely with open-source, local-first components without relying on paid APIs or cloud services. The system successfully ingests YouTube playlists and PDFs, processes them through a multi-step pipeline, and enables meaningful semantic search with provenance — connecting search results back to the exact video timestamp or PDF page.

The project represents 13 implementation phases covering full-stack development, database design, AI integration, security implementation, and comprehensive testing. The resulting system is a functional educational tool that addresses a real study problem for students using YouTube-based learning resources.
