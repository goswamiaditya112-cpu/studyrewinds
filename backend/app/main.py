from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings
from app.db.session import get_db
from app.api.auth import router as auth_router
from app.api.subjects import router as subjects_router
from app.api.playlists import router as playlists_router
from app.api.transcripts import router as transcripts_router
from app.api.documents import router as documents_router
from app.api.search import router as search_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="StudyRewinds - Local AI Study Assistant Foundation & Auth",
    version="0.4.0",
)

# Configure CORS for local React frontend (Vite default port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Authentication Routers
app.include_router(auth_router, prefix="/api")
app.include_router(auth_router, prefix="/api/v1")

# Register Subject Routers
app.include_router(subjects_router, prefix="/api")
app.include_router(subjects_router, prefix="/api/v1")

# Register Playlist Routers
app.include_router(playlists_router, prefix="/api")
app.include_router(playlists_router, prefix="/api/v1")

# Register Transcript Routers
app.include_router(transcripts_router, prefix="/api")
app.include_router(transcripts_router, prefix="/api/v1")

# Register Document / Study Material Routers
app.include_router(documents_router, prefix="/api")
app.include_router(documents_router, prefix="/api/v1")

# Register Semantic Search Routers
app.include_router(search_router, prefix="/api")
app.include_router(search_router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENV,
    }

@app.get("/health/db", tags=["Health"])
def db_health_check(db: Session = Depends(get_db)):
    try:
        pg_ver = db.execute(text("SELECT version();")).scalar()
        vector_ext = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
        ).scalar()
        return {
            "status": "healthy",
            "database": "postgresql",
            "pgvector_installed": vector_ext is not None,
            "pgvector_version": vector_ext,
            "pg_version": pg_ver,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }
