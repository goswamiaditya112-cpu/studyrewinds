import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select
import jwt

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.models.user import User

def test_registration_success(client: TestClient, db_session: Session):
    """Test A & B & C: Registration succeeds, hashes password with Argon2id, and hides secrets."""
    payload = {
        "email": "student_alice@example.com",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    # Verify response structure
    assert "id" in data
    assert data["email"] == "student_alice@example.com"
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify database persistence & password hashing
    user = db_session.execute(
        select(User).where(User.email == "student_alice@example.com")
    ).scalar_one_or_none()
    assert user is not None
    assert user.hashed_password != "SecurePassword123!"
    assert user.hashed_password.startswith("$argon2id$")

def test_registration_duplicate_email(client: TestClient):
    """Test D: Duplicate email registration returns 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "Password12345",
    }
    res1 = client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/auth/register", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()

def test_registration_case_insensitive_duplicate(client: TestClient):
    """Test case-insensitive email duplicate check."""
    client.post("/api/auth/register", json={"email": "case@example.com", "password": "Password12345"})
    res = client.post("/api/auth/register", json={"email": "CASE@EXAMPLE.COM", "password": "Password12345"})
    assert res.status_code == 409

def test_registration_invalid_email(client: TestClient):
    """Test E: Invalid email format is rejected with 422."""
    response = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "ValidPassword123"},
    )
    assert response.status_code == 422

def test_registration_too_short_password(client: TestClient):
    """Test F: Passwords shorter than 8 characters are rejected with 422."""
    response = client.post(
        "/api/auth/register",
        json={"email": "short_pw@example.com", "password": "short"},
    )
    assert response.status_code == 422

def test_registration_empty_password(client: TestClient):
    """Test F: Empty or whitespace-only password is rejected."""
    response = client.post(
        "/api/auth/register",
        json={"email": "empty_pw@example.com", "password": "        "},
    )
    assert response.status_code == 422

def test_login_success(client: TestClient):
    """Test G, J, K: Login succeeds with correct credentials, returns Bearer JWT."""
    client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": "MySecretPassword123"},
    )

    login_res = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "MySecretPassword123"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert "user" in data
    assert data["user"]["email"] == "bob@example.com"
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]

def test_login_invalid_password(client: TestClient):
    """Test H: Login fails with wrong password (401)."""
    client.post(
        "/api/auth/register",
        json={"email": "charlie@example.com", "password": "CorrectPassword123"},
    )

    res = client.post(
        "/api/auth/login",
        json={"email": "charlie@example.com", "password": "WrongPassword999"},
    )
    assert res.status_code == 401
    assert "invalid email or password" in res.json()["detail"].lower()

def test_login_nonexistent_user(client: TestClient):
    """Test I: Login fails for nonexistent user (401)."""
    res = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "Password123"},
    )
    assert res.status_code == 401
    assert "invalid email or password" in res.json()["detail"].lower()

def test_me_endpoint_success(client: TestClient):
    """Test L & P & R: /api/auth/me returns current authenticated user details."""
    reg = client.post(
        "/api/auth/register",
        json={"email": "dave@example.com", "password": "DavePassword123"},
    )
    user_id = reg.json()["id"]

    login = client.post(
        "/api/auth/login",
        json={"email": "dave@example.com", "password": "DavePassword123"},
    )
    token = login.json()["access_token"]

    me_res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["id"] == user_id
    assert me_data["email"] == "dave@example.com"
    assert "hashed_password" not in me_data

def test_me_endpoint_missing_token(client: TestClient):
    """Test M: /api/auth/me rejects missing Authorization header with 401."""
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert "missing" in res.json()["detail"].lower()

def test_me_endpoint_invalid_token(client: TestClient):
    """Test N: /api/auth/me rejects garbage/malformed JWT with 401."""
    res = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert res.status_code == 401
    assert "invalid or expired" in res.json()["detail"].lower()

def test_me_endpoint_expired_token(client: TestClient):
    """Test O: /api/auth/me rejects expired JWT with 401."""
    fake_user_id = str(uuid.uuid4())
    # Generate token that expired 1 hour ago
    expired_token = create_access_token(
        subject=fake_user_id,
        expires_delta=timedelta(hours=-1),
    )

    res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401
    assert "invalid or expired" in res.json()["detail"].lower()

def test_me_endpoint_nonexistent_user_in_token(client: TestClient):
    """Test Q: A validly-signed token referencing a nonexistent user is rejected with 401."""
    random_user_id = str(uuid.uuid4())
    valid_token = create_access_token(subject=random_user_id)

    res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert res.status_code == 401
    assert "user not found" in res.json()["detail"].lower()

def test_jwt_payload_does_not_contain_secrets():
    """Verify that generated JWT tokens contain only sub, iat, exp and no sensitive data."""
    test_id = str(uuid.uuid4())
    token = create_access_token(subject=test_id)
    payload = decode_access_token(token)

    assert payload["sub"] == test_id
    assert "password" not in payload
    assert "hashed_password" not in payload
    assert "email" not in payload
