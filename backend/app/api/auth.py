from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password, create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new student user",
)
@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def register(data: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user with email and secure password.
    Rejects duplicate emails with 409 Conflict.
    Hashes password using Argon2id before storage.
    """
    clean_email = data.email.strip().lower()

    # Check for existing email (case-insensitive)
    existing_user = db.execute(
        select(User).where(User.email == clean_email)
    ).scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Hash password securely with Argon2id
    hashed = hash_password(data.password)

    user = User(
        email=clean_email,
        hashed_password=hashed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and obtain a JWT access token",
)
def login(data: UserLoginRequest, db: Session = Depends(get_db)):
    """
    Verify user credentials and return a signed Bearer JWT token.
    Rejects invalid credentials with 401 Unauthorized.
    """
    clean_email = data.email.strip().lower()

    user = db.execute(
        select(User).where(User.email == clean_email)
    ).scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT token with user UUID as sub
    access_token = create_access_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        user=UserResponse.model_validate(user),
    )

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user",
)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Protected endpoint returning safe details for the authenticated user.
    Requires a valid Bearer token in the Authorization header.
    """
    return current_user

@router.post(
    "/logout",
    summary="Log out the current user session",
)
def logout():
    """
    Client discards the JWT Bearer token upon logout.
    """
    return {"status": "ok", "message": "Logged out successfully"}
