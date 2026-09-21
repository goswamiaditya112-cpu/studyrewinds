import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "StudyRewinds"
    ENV: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://studyrewind:change-me@localhost:5432/studyrewinds_dev"
    TEST_DATABASE_URL: str = "postgresql+psycopg://studyrewind:change-me@localhost:5432/studyrewinds_test"

    # JWT Authentication Settings
    JWT_SECRET_KEY: str = "studyrewinds-super-secure-jwt-secret-key-change-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Document Storage Settings
    STORAGE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "documents"))
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
