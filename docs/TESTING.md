# StudyRewind — Testing Documentation

## Overview

The backend test suite uses **pytest** with **httpx** (async-compatible HTTP client for FastAPI testing). Tests run against a real PostgreSQL database (test database) with the pgvector extension installed.

---

## Running Tests

```bash
# From the project root directory
set PYTHONPATH=backend
.\venv\Scripts\python.exe -m pytest backend/tests -q
```

**Expected result:** `184 passed, 0 failed`

```bash
# Verbose output
.\venv\Scripts\python.exe -m pytest backend/tests -v

# Run a specific test file
.\venv\Scripts\python.exe -m pytest backend/tests/test_auth.py -v

# Run a specific test class
.\venv\Scripts\python.exe -m pytest backend/tests/test_transcripts.py::TestWhisperTempDirCleanup -v
```

---

## Test Files

| File | Tests | What It Covers |
|---|---|---|
| `test_health.py` | ~3 | Backend health, database health, pgvector presence |
| `test_auth.py` | ~15 | Registration, login, token validation, duplicate email |
| `test_subjects.py` | ~20 | Subject CRUD, ownership, validation |
| `test_playlists.py` | ~25 | Playlist import, video discovery, ownership |
| `test_transcripts.py` | ~30 | Transcript processing, chunking, Whisper cleanup, idempotency |
| `test_documents.py` | ~20 | PDF upload, processing, page extraction |
| `test_embedding.py` | ~20 | Embedding generation, validation, batching, dimension checks |
| `test_vector_storage.py` | ~20 | pgvector persistence, idempotency, batch embedding |
| `test_search.py` | ~25 | Semantic search, subject scoping, ranking, ownership |
| `test_pgvector.py` | ~8 | pgvector extension, cosine distance operator |
| `test_schema.py` | ~10 | Database schema integrity, cascade deletes, constraints |
| `test_phase12_security_hardening.py` | ~30 | IDOR prevention, cross-user isolation, auth boundary tests |
| `verify_clean_db_migration.py` | — | Migration verification script |

---

## Test Configuration

`conftest.py` provides shared pytest fixtures:

- **Database:** Each test gets a fresh database session with automatic rollback after the test completes. No test data persists between tests.
- **Test client:** `httpx.AsyncClient` or `fastapi.testclient.TestClient` against the FastAPI app.
- **Test users:** Fixtures create test users with known credentials for authentication tests.

---

## What Each Test Suite Covers

### `test_auth.py`
- Register with valid email/password → 201 Created
- Register with duplicate email → 409 Conflict
- Login with correct credentials → JWT token returned
- Login with wrong password → 401 Unauthorized
- Access protected endpoint without token → 401
- Access protected endpoint with expired token → 401

### `test_subjects.py`
- Create subject → 201
- List subjects → only current user's subjects returned
- Get subject → 404 if belongs to another user
- Update subject → 404 if belongs to another user
- Delete subject → cascades to playlists, videos, chunks

### `test_transcripts.py`
- Process video → chunks created with correct timestamps
- Idempotency: processing same video twice returns existing chunks
- `TestWhisperTempDirCleanup` class:
  - Cleanup succeeds on first attempt
  - Cleanup succeeds after one OSError
  - Logs warning after all retry attempts fail
  - `onerror` handler clears read-only file attributes

### `test_embedding.py`
- Single text embedding → 384 dimensions
- Empty string → InvalidInputError
- None input → InvalidInputError
- Batch embedding → correct count returned
- Dimension validation → EmbeddingDimensionError on wrong size
- Non-finite values → EmbeddingServiceError

### `test_phase12_security_hardening.py`
- User A cannot read User B's subjects (returns 404)
- User A cannot read User B's playlists (returns 404)
- User A cannot process User B's videos (returns 404)
- User A cannot search User B's subjects (returns 404)
- All protected endpoints return 401 without token

---

## Test Philosophy

Tests in this project:

1. **Test real behavior** — no excessive mocking of database or business logic
2. **Test ownership boundaries** — every resource type has cross-user isolation tests
3. **Test failure paths** — not just the happy path but also invalid input, wrong credentials, missing resources
4. **Are independent** — each test cleans up after itself; no shared state between tests
5. **Are fast** — the suite runs in ~105 seconds including embedding model loading

---

## Baseline

The passing baseline as of the project freeze is:

```
184 passed, 0 failed
```

Any regression from this baseline indicates a broken change.
