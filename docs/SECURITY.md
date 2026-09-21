# StudyRewind — Security Documentation

## Overview

StudyRewind implements authentication and authorization throughout the backend. Every API endpoint that accesses user data is protected. Users can only access their own subjects, playlists, videos, transcripts, documents, and search results.

---

## Authentication

### Password Hashing — Argon2id

```python
from argon2 import PasswordHasher
_password_hasher = PasswordHasher()

def hash_password(password: str) -> str:
    return _password_hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _password_hasher.verify(hashed_password, plain_password)
```

Passwords are hashed using **Argon2id** (via `argon2-cffi`), which is the winner of the Password Hashing Competition (2015) and is recommended by OWASP as the first choice for password hashing.

**Why Argon2id?**
- Memory-hard: resistant to GPU-based brute-force attacks
- Time-configurable: can tune difficulty to require more computation
- Side-channel resistant: combines Argon2i and Argon2d properties
- Produces PHC string format hashes (includes algorithm, parameters, and salt in one string)

Plaintext passwords are never stored and are not retained in memory after verification.

---

### JWT Access Tokens

```python
import jwt

def create_access_token(subject: str, expires_delta=None) -> str:
    payload = {
        "sub": str(subject),  # user UUID
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

After login, the backend issues a **JSON Web Token (JWT)** containing the user's UUID as the `sub` claim.

**Token properties:**
- Algorithm: configurable (set in environment — typically HS256)
- Expiry: configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`
- Payload: user UUID (`sub`), issued-at (`iat`), expiry (`exp`)
- Storage: client-side (localStorage in the browser)

**Token validation:** Every protected endpoint uses a FastAPI `Depends(get_current_user)` dependency that decodes and validates the JWT before the route handler runs.

---

## Authorization — Ownership Enforcement

### The Ownership Chain

```
User
 └── Subject (user_id FK)
      ├── Playlist (subject_id FK)
      │    └── Video (playlist_id FK)
      │         └── TranscriptChunk (video_id FK)
      └── Document (subject_id FK)
           └── DocumentChunk (document_id FK)
```

Every resource belongs to a user through this chain. The backend verifies ownership at every level.

---

### IDOR Prevention

**IDOR (Insecure Direct Object Reference)** is a vulnerability where a user can access another user's data by guessing or incrementing an ID.

StudyRewind prevents IDOR by:

1. **Ownership check on every request:** Before returning any resource, the backend verifies it belongs to the authenticated user.

2. **404 instead of 403:** When a resource exists but belongs to a different user, the API returns `404 Not Found` rather than `403 Forbidden`. This prevents an attacker from confirming that a resource ID exists.

3. **UUID primary keys:** All IDs are randomly generated UUIDs (not sequential integers). An attacker cannot enumerate or guess valid IDs.

**Example — Video transcript request:**
```
GET /api/v1/videos/{video_id}/transcript

Backend checks:
  video.playlist.subject.user_id == current_user.id
  If not: return 404 (not 403)
```

---

## Security Test Coverage

The test suite includes a dedicated security hardening test file (`test_phase12_security_hardening.py`, 30,290 bytes) that tests:

- **Cross-user resource isolation:** User A cannot read User B's subjects, playlists, videos, or transcripts
- **Authorization boundary tests:** Unauthenticated requests to protected endpoints return 401
- **IDOR tests:** Requests for existing resources that belong to other users return 404
- **Token manipulation:** Invalid, expired, or tampered tokens are rejected

---

## Input Validation

**Request validation** is handled by Pydantic schemas (FastAPI's built-in validation):
- Email addresses are validated using `email-validator`
- Passwords are validated for minimum length
- UUIDs are validated as proper UUID format
- String fields have maximum length constraints matching database column sizes

**SQL injection:** SQLAlchemy ORM with parameterized queries prevents SQL injection. Raw SQL strings are not used for user input.

---

## CORS Configuration

The backend only accepts cross-origin requests from known local development origins:

```python
allow_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
```

All other origins are rejected.

---

## Known Security Limitations

| Limitation | Notes |
|---|---|
| **No HTTPS** | Current setup is HTTP-only (localhost). Production deployment would require TLS. |
| **JWT stored in localStorage** | Vulnerable to XSS. A production implementation would use HttpOnly cookies. |
| **No token revocation** | JWT tokens are valid until expiry. There is no logout blacklist. |
| **No rate limiting** | API endpoints do not have per-IP rate limits. |
| **No email verification** | User registration does not verify email ownership. |

These are accepted limitations for a college project running on localhost. They are documented here rather than silently ignored.
