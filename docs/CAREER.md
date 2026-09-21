# StudyRewind — Career Materials

---

## CV / Resume Project Description

### Full Version (for resume body)

**StudyRewind — AI-Powered Educational Search Assistant** *(Final Year Project)*

Built a full-stack web application that ingests YouTube lecture playlists and PDF study materials, transcribes and embeds content locally using AI, and provides semantic search with timestamp and page provenance.

**Backend:** FastAPI (Python), PostgreSQL, pgvector, SQLAlchemy 2.0, Alembic, Argon2id authentication, JWT authorization

**AI/ML:** faster-whisper (local speech transcription), sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`, 384-d embeddings), pgvector cosine similarity search, yt-dlp, youtube-transcript-api, pypdf

**Frontend:** React 18, TypeScript, Vite

**Key engineering work:**
- Implemented a three-step transcript extraction pipeline: YouTube captions → yt-dlp subtitle download → local Whisper AI fallback
- Built a local embedding pipeline generating 384-dimensional multilingual vectors (Hindi + English) with batch processing, idempotency, and validation
- Implemented strict user data isolation with IDOR prevention and UUID-based ownership chains across all API endpoints
- Wrote 184 passing automated tests covering authentication, subject management, transcription, PDF processing, semantic search, and security boundaries
- Resolved a Windows file-locking bug in temporary audio cleanup using bounded retry with read-only attribute handling

---

### Short Version (for resume bullet points — pick 3–4)

- Designed and built a semantic search engine over YouTube transcripts and PDF notes using PostgreSQL + pgvector and 384-d local embeddings (paraphrase-multilingual-MiniLM-L12-v2)
- Implemented a three-step transcript extraction pipeline (YouTube captions → yt-dlp → faster-whisper) with automatic fallback and timestamp preservation
- Built JWT authentication with Argon2id password hashing and IDOR-safe ownership enforcement across all API endpoints
- Achieved 184/184 passing automated tests across authentication, search, transcription, PDF processing, and security hardening test suites

---

### One-Line Version (for LinkedIn / portfolio tagline)

> Full-stack AI study assistant: YouTube + PDF ingestion, local speech transcription (Whisper), multilingual semantic search (pgvector + sentence-transformers), FastAPI + React — zero paid APIs.

---

## Portfolio-Ready Project Summary

### StudyRewind

**What it is:**
StudyRewind is a web application that transforms YouTube lecture playlists and PDF study notes into a searchable knowledge base. Students can type a natural language question and find the exact moment in a lecture video or the exact page in a textbook where a concept is explained.

**The problem it solves:**
Engineering and science students in India commonly study from long YouTube lecture series (200–700 videos per subject). Finding a specific concept requires scrubbing through hours of video. StudyRewind eliminates this by making all lecture content searchable by meaning.

**How it works:**
1. Students import any public YouTube playlist or upload PDF notes
2. StudyRewind transcribes video audio using local Whisper AI and extracts PDF text using pypdf
3. Content is split into chunks and converted to 384-dimensional vectors using a local multilingual model
4. Vectors are stored in PostgreSQL with the pgvector extension
5. Students type natural language queries, which are also vectorized, and the system returns the most semantically similar transcript chunks and PDF sections with timestamps and page numbers

**What makes it technically interesting:**
- Entirely local AI pipeline — no paid APIs, no cloud AI services
- Three-level transcription fallback: YouTube captions → yt-dlp subtitle download → Whisper
- Supports Hindi and English content (Indian educational YouTube content)
- Strict security: Argon2id passwords, JWT auth, ownership-based authorization, IDOR prevention
- 184 automated tests including a security hardening test suite

**Technology:**
FastAPI · PostgreSQL · pgvector · React + TypeScript · faster-whisper · sentence-transformers · yt-dlp · SQLAlchemy · Alembic · Argon2id · PyJWT

---

## Internship / Job Application Description

### For a Backend / Python role:

> Built StudyRewind, a FastAPI backend application serving a React frontend. Designed and implemented a PostgreSQL schema with pgvector for vector similarity search. Wrote a multi-step YouTube transcript extraction pipeline with automatic fallbacks. Implemented local batch embedding generation with idempotency and validation. Secured all endpoints with Argon2id password hashing, JWT tokens, and ownership-based authorization. Wrote 184 automated tests with pytest and httpx.

### For an AI/ML role:

> Built a local AI-powered semantic search system for educational content. Integrated faster-whisper (CPU int8 Whisper model) for speech-to-text transcription. Used sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) for 384-d multilingual embedding generation. Stored and queried vectors using pgvector cosine distance search. All inference runs locally with no external API dependencies.

### For a Full-Stack role:

> Built a full-stack web application (React + TypeScript frontend, FastAPI backend, PostgreSQL + pgvector database) that ingests YouTube playlists and PDFs, transcribes and embeds content locally using AI, and provides semantic search with video timestamp and PDF page provenance.

---

## GitHub Repository Description (for About section)

> AI-powered study assistant — semantic search over YouTube transcripts and PDF notes using local Whisper transcription, sentence-transformers embeddings, and PostgreSQL + pgvector. No paid APIs. FastAPI + React + TypeScript.

### GitHub Topics / Tags

```
semantic-search  pgvector  fastapi  react  typescript  whisper  sentence-transformers
python  postgresql  youtube  yt-dlp  embeddings  educational-ai  nlp  local-ai
```
