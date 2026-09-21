# StudyRewind — Database Documentation

## Overview

StudyRewind uses PostgreSQL with the pgvector extension. The schema has 7 tables organized around a clear ownership hierarchy from user down to individual content chunks.

---

## Entity-Relationship Diagram

```
users
  │
  └──< subjects (user_id FK)
         │
         ├──< playlists (subject_id FK)
         │       │
         │       └──< videos (playlist_id FK)
         │               │
         │               └──< transcript_chunks (video_id FK)
         │                       ├── start_time
         │                       ├── end_time
         │                       ├── text
         │                       └── embedding  vector(384)
         │
         └──< documents (subject_id FK)
                 │
                 └──< document_chunks (document_id FK)
                         ├── page_number
                         ├── chunk_index
                         ├── text
                         └── embedding  vector(384)
```

---

## Table Definitions

### `users`

Stores registered accounts. Each user owns their own subjects and all data under them.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Auto-generated with uuid4 |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL, INDEX | Login identifier |
| `hashed_password` | VARCHAR(255) | NOT NULL | Argon2id hash |
| `created_at` | TIMESTAMPTZ | NOT NULL | UTC timestamp |

---

### `subjects`

Academic subjects created by a user (e.g., "Operating Systems", "DBMS").

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Auto-generated |
| `user_id` | UUID | FK → users.id CASCADE | Owner |
| `name` | VARCHAR(255) | NOT NULL | e.g., "Computer Networks" |
| `description` | TEXT | NULLABLE | Optional description |
| `created_at` | TIMESTAMPTZ | NOT NULL | UTC timestamp |

---

### `playlists`

YouTube playlists imported into a subject.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Auto-generated |
| `subject_id` | UUID | FK → subjects.id CASCADE | Parent subject |
| `youtube_playlist_id` | VARCHAR(100) | NOT NULL | e.g., `PLxCzCOWd7ai...` |
| `title` | VARCHAR(255) | NOT NULL | Fetched from YouTube |
| `status` | VARCHAR(50) | NOT NULL, DEFAULT 'pending' | pending / active |
| `created_at` | TIMESTAMPTZ | NOT NULL | UTC timestamp |

**Unique constraint:** `(subject_id, youtube_playlist_id)` — prevents importing the same playlist twice into the same subject.

---

### `videos`

Individual YouTube videos discovered within a playlist.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Auto-generated |
| `playlist_id` | UUID | FK → playlists.id CASCADE | Parent playlist |
| `youtube_video_id` | VARCHAR(50) | NOT NULL | e.g., `kBdlM6hNDAE` |
| `title` | VARCHAR(255) | NOT NULL | Fetched from YouTube |
| `duration_seconds` | INTEGER | NULLABLE | Video duration |
| `transcript_source` | VARCHAR(50) | NOT NULL, DEFAULT 'none' | none / caption / subtitle / whisper |
| `status` | VARCHAR(50) | NOT NULL, DEFAULT 'pending' | pending / processing / completed / failed |
| `error_message` | TEXT | NULLABLE | Error detail if failed |
| `created_at` | TIMESTAMPTZ | NOT NULL | UTC timestamp |

**Unique constraint:** `(playlist_id, youtube_video_id)` — prevents the same video appearing twice in the same playlist.

**`transcript_source` values:**
- `none` — not yet processed
- `caption` — captions retrieved via youtube-transcript-api
- `subtitle` — subtitle file downloaded via yt-dlp
- `whisper` — local Whisper AI transcription

---

### `transcript_chunks`

60–90 second timestamped text windows from a video's transcript. Contains the embedding vector for semantic search.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Auto-generated |
| `video_id` | UUID | FK → videos.id CASCADE | Parent video |
| `start_time` | FLOAT | NOT NULL | Seconds from video start |
| `end_time` | FLOAT | NOT NULL | Seconds from video start |
| `text` | TEXT | NOT NULL | Transcript text for this window |
| `embedding` | vector(384) | NOT NULL | 384-d normalized embedding |
| `created_at` | TIMESTAMPTZ | NOT NULL | UTC timestamp |

**Note on the default embedding:** The schema default is `[0.0] * 384` (a zero vector). The vector storage service uses this to detect un-embedded chunks: any chunk with L2 norm close to 0 needs embedding.

---

### `documents`

Uploaded PDF files attached to a subject.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Auto-generated |
| `subject_id` | UUID | FK → subjects.id CASCADE | Parent subject |
| `filename` | VARCHAR(255) | NOT NULL | Original filename |
| `file_path` | VARCHAR(500) | NOT NULL | Storage path on disk |
| `page_count` | INTEGER | NOT NULL, DEFAULT 0 | Total pages in PDF |
| `status` | VARCHAR(50) | NOT NULL, DEFAULT 'pending' | pending / processing / completed / failed |
| `error_message` | TEXT | NULLABLE | Error detail if failed |
| `created_at` | TIMESTAMPTZ | NOT NULL | UTC timestamp |

---

### `document_chunks`

Page-aware text chunks from a PDF document. Contains the embedding vector for semantic search.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Auto-generated |
| `document_id` | UUID | FK → documents.id CASCADE | Parent document |
| `page_number` | INTEGER | NOT NULL | Source PDF page |
| `chunk_index` | INTEGER | NOT NULL | Position within page |
| `text` | TEXT | NOT NULL | Extracted text |
| `embedding` | vector(384) | NOT NULL | 384-d normalized embedding |
| `created_at` | TIMESTAMPTZ | NOT NULL | UTC timestamp |

---

## CASCADE Delete Behavior

All foreign keys are defined with `ON DELETE CASCADE`. This means:

| If you delete... | Also deleted automatically |
|---|---|
| A `user` | All their subjects, playlists, videos, chunks, documents |
| A `subject` | All its playlists, videos, chunks, documents |
| A `playlist` | All its videos and transcript chunks |
| A `video` | All its transcript chunks |
| A `document` | All its document chunks |

This ensures referential integrity without manual cleanup code.

---

## pgvector Extension

The `vector(384)` column type is provided by the pgvector PostgreSQL extension.

**Cosine distance operator:**
```sql
-- Returns cosine distance (0 = identical direction, 1 = opposite)
SELECT * FROM transcript_chunks
ORDER BY embedding <=> '[0.1, 0.3, ...]'::vector
LIMIT 10;
```

**Why cosine similarity?**
All embeddings are normalized to unit vectors (L2 norm = 1.0). For unit vectors, cosine similarity and dot product are equivalent. Cosine distance measures the angle between two vectors — a small angle means the texts have similar meaning.

---

## Migrations

Database schema changes are managed with Alembic:

```bash
# Apply all migrations
alembic -c backend/alembic.ini upgrade head

# Check current revision
alembic -c backend/alembic.ini current
```

---

## Connection

The backend connects to PostgreSQL using psycopg v3 (the modern async-compatible PostgreSQL driver for Python):

```
DATABASE_URL=postgresql+psycopg://studyrewind:change-me@localhost:5432/studyrewinds_dev
```
