from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
from alembic.config import Config
from alembic import command

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

test_engine = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Run Alembic upgrade head on the clean test database before tests."""
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    alembic_dir = backend_dir / "alembic"
    
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.TEST_DATABASE_URL)
    
    # Run migration from empty database to head
    command.upgrade(alembic_cfg, "head")
    
    yield
    
    # Clean up test data after test suite
    with test_engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE users CASCADE;"))
        conn.commit()

@pytest.fixture(scope="function")
def db_session() -> Session:
    """Yields a database session that cleans up after each test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text("TRUNCATE TABLE users CASCADE;"))
        session.commit()
        session.close()

@pytest.fixture(scope="function")
def client(db_session: Session) -> TestClient:
    """FastAPI test client with test db session dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
