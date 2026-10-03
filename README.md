# StudyRewinds

**StudyRewinds** is a local-first, AI-powered study assistant designed for college students. It enables students to organize course material across YouTube playlists and PDF lecture notes, index timestamped transcripts and page-numbered text using local embeddings, and query their materials with semantic vector search.

---

## 📺 Project Demo Video

Click below to watch the live demonstration of StudyRewind in action:

[![StudyRewind Demo Video](https://img.youtube.com/vi/5xIW6lkczRc/maxresdefault.jpg)](https://youtu.be/5xIW6lkczRc)

> **[▶ Watch Live Demo on YouTube](https://youtu.be/5xIW6lkczRc)**

---

## Phase 1: Foundation & Database Layer (Frozen)

- Modular FastAPI backend foundation.
- PostgreSQL integration with the `pgvector` extension.
- SQLAlchemy 2.0 ORM models with UUID primary keys and cascading foreign-key deletion.
- Version-controlled Alembic migrations (`vector(384)` with HNSW cosine distance indexing).
- Verified from clean empty database.

---

## Phase 2: Authentication & User Security

Phase 2 establishes a secure, local-first authentication system and identity layer:

- **Password Hashing**: Secure Argon2id password hashing via `argon2-cffi` (RFC 9106 recommended).
- **JWT Bearer Authentication**: Signed JSON Web Tokens (`PyJWT`, HS256) loaded from environment configuration (`JWT_SECRET_KEY`).
- **User Ownership Foundation**: Reusable FastAPI dependency `get_current_user` resolving token `sub` (User UUID) against PostgreSQL.
- **Frontend Design Preservation**: Existing React + Vite frontend preserved 100% and connected to the backend auth endpoints with the official StudyRewind logo.

### Authentication Endpoints

| Method | Endpoint             | Description                                                                 | Protected        |
| :----- | :------------------- | :-------------------------------------------------------------------------- | :--------------- |
| `POST` | `/api/auth/register` | Register a new user (email, password >= 8 chars). Rejects duplicates (409). | No               |
| `POST` | `/api/auth/login`    | Log in and receive a signed Bearer JWT access token.                        | No               |
| `GET`  | `/api/auth/me`       | Fetch authenticated user profile (`id`, `email`, `created_at`).             | Yes (Bearer JWT) |
| `POST` | `/api/auth/logout`   | Discard user session.                                                       | No               |

_(Note: Endpoints are also aliased under `/api/v1/auth/_` for frontend compatibility).\*

---

## Project Structure

```text
studyrewinds/
+-- backend/
�   +-- alembic/
�   �   +-- versions/
�   �   �   +-- 001_initial_schema.py   # Initial migration for tables & pgvector
�   �   +-- env.py                      # Dynamic migration environment
�   �   +-- script.py.mako              # Migration template
�   +-- app/
�   �   +-- api/                        # API route controllers
�   �   �   +-- auth.py                 # Phase 2: Registration, login, /me, logout
�   �   �   +-- deps.py                 # Phase 2: get_current_user dependency
�   �   +-- core/
�   �   �   +-- config.py               # Settings (JWT_SECRET_KEY, DATABASE_URL)
�   �   �   +-- security.py             # Phase 2: Argon2id hashing & JWT encode/decode
�   �   +-- db/
�   �   �   +-- base.py                 # DeclarativeBase
�   �   �   +-- session.py              # Engine & SessionLocal
�   �   +-- models/                     # SQLAlchemy ORM models
�   �   �   +-- user.py                 # users table
�   �   �   +-- subject.py              # subjects table
�   �   �   +-- playlist.py             # playlists table
�   �   �   +-- video.py                # videos table
�   �   �   +-- document.py             # documents table
�   �   �   +-- chunk.py                # transcript_chunks & document_chunks (vector 384)
�   �   +-- schemas/                    # Pydantic validation schemas
�   �   �   +-- auth.py                 # Phase 2: UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse
�   �   +-- main.py                     # FastAPI entrypoint (/health, /health/db, /api/auth)
�   +-- tests/
�   �   +-- conftest.py                 # Fixtures & automated test-db migration runner
�   �   +-- test_auth.py                # Phase 2: 15 Auth & Security test cases
�   �   +-- test_health.py              # Health endpoints tests
�   �   +-- test_schema.py              # Foreign keys, cascades & uniqueness tests
�   �   +-- test_pgvector.py            # 384-dim vector insertion & cosine distance tests
�   �   +-- verify_clean_db_migration.py # Standalone clean DB verification script
�   +-- alembic.ini                     # Alembic configuration
�   +-- requirements.txt                # Python dependencies
+-- frontend/                           # Preserved React + TypeScript + Vite frontend
�   +-- public/
�   �   +-- logo.png                    # Official StudyRewind Logo
�   +-- src/
�   �   +-- components/brand/
�   �   �   +-- StudyRewindLogo.tsx     # Official logo component
�   �   +-- App.tsx                     # Existing UI with auth token persistence
�   �   +-- styles.css                  # Existing styles & design system
�   +-- package.json
�   +-- vite.config.ts
+-- .env.example                        # Template environment variables
+-- .gitignore                          # Excludes secrets, venvs, and cache
+-- README.md                           # Documentation
```

---

## Environment Configuration

In `.env`:

```ini
PROJECT_NAME="StudyRewinds"
ENV="development"

# PostgreSQL Connection
DATABASE_URL="postgresql+psycopg://studyrewind:change-me@localhost:5432/studyrewinds_dev"
TEST_DATABASE_URL="postgresql+psycopg://studyrewind:change-me@localhost:5432/studyrewinds_test"

# JWT Authentication
JWT_SECRET_KEY="replace-with-a-long-random-secret"
JWT_ALGORITHM="HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

---

## Running the Application

### 1. Start the Backend API

```powershell
$env:PYTHONPATH="backend"
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive Swagger UI: `http://127.0.0.1:8000/docs`

### 2. Start the React Frontend

```powershell
cd frontend
npm run dev
```

Access frontend: `http://localhost:5173`

### 3. Running Automated Tests

```powershell
$env:PYTHONPATH="backend"
.\venv\Scripts\python.exe -m pytest -v backend/tests
```
