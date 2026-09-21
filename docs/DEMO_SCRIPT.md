# StudyRewind — Demo Script

## Purpose

This script demonstrates the complete StudyRewind workflow from login to semantic search. Use this for project demonstrations, viva voce, or recording a screen demo video.

**Total demo time:** approximately 5–8 minutes (excluding transcript processing time)

---

## Before Starting

Ensure the following are running:

```bash
# 1. Start PostgreSQL
docker start backend-postgres-1

# 2. Start backend (in one terminal)
set PYTHONPATH=backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000

# 3. Start frontend (in another terminal)
cd frontend
npm run dev
```

Open browser: `http://localhost:5173`

---

## Demo Flow

### Scene 1 — Login

**Action:** Open the browser. Show the StudyRewind landing/login page.

**Say:**
> "StudyRewind is a study assistant that lets students search through their lecture videos and PDF notes using natural language. Let me log in."

**Action:** Enter credentials:
- Email: `alex.student@college.edu`
- Password: `StudyRewind2025!`

Click **Login**. Dashboard appears.

---

### Scene 2 — Dashboard

**Action:** Show the dashboard.

**Say:**
> "This is the dashboard. I can see all my subjects here. Each subject is a course I'm studying — like DBMS or Operating Systems. Let me open DBMS."

**Action:** Click on the **DBMS** subject.

---

### Scene 3 — Subject Workspace

**Action:** Show the subject workspace with playlists and materials visible.

**Say:**
> "Inside this subject, I've imported a YouTube playlist from Gate Smashers — a popular Indian engineering education channel. The videos are listed here with their processing status."

**Action:** Point to the video list, show some as "Available" (completed).

---

### Scene 4 — Individual Video Transcript

**Action:** Click on a video that has status **Available**.

**Say:**
> "For each video, StudyRewind has extracted the transcript and broken it into 60 to 90 second chunks. Each chunk has a start time and end time."

**Action:** Show the transcript chunks with timestamps.

**Say:**
> "If I click the timestamp, it opens the YouTube video at exactly that moment."

---

### Scene 5 — Processing a New Video (optional, if time allows)

**Action:** Find a video with status **Queued** or **Pending**. Click **Retrieve**.

**Say:**
> "Let me show the processing happening live. StudyRewind first tries to get YouTube's free captions. If that's blocked, it downloads the subtitle file. If neither works, it falls back to running Whisper AI locally on my laptop to transcribe the audio. All of this happens on my machine — no paid APIs."

**Wait** for processing to complete (~1–2 minutes on CPU). Status changes to **Available**.

---

### Scene 6 — Semantic Search (Main Feature)

**Action:** Navigate to the Search section within the DBMS subject.

**Say:**
> "Now the main feature. I'm going to search using a natural language question — not exact keywords."

**Action:** Type: `what is normalization in databases?`

Click **Search**.

**Say:**
> "StudyRewind converts my question into a mathematical vector using a local AI model. It then finds the transcript chunks and document sections whose vectors are closest to my query vector. This is semantic search — it matches by meaning, not exact words."

**Action:** Show the results appearing with scores, video titles, and timestamps.

**Say:**
> "Each result shows which video it came from and at what timestamp. I can click the timestamp to jump straight to that moment in the YouTube video."

---

### Scene 7 — PDF Material (if demo includes PDF)

**Action:** Navigate to Study Materials section. Show an uploaded PDF.

**Say:**
> "I can also upload PDF notes or textbook chapters. StudyRewind extracts text page by page and makes it searchable too."

**Action:** Run a search. Show a PDF result appearing alongside video results.

**Say:**
> "PDF results tell me exactly which page to open. Video results tell me exactly which timestamp to jump to."

---

### Scene 8 — Closing

**Say:**
> "StudyRewind runs entirely on a laptop. No paid AI services, no cloud APIs. The embedding model and Whisper both run locally. The vector search uses PostgreSQL with the pgvector extension — no separate vector database needed.

> The system doesn't generate answers. It retrieves the most relevant parts of the material the student has already uploaded. This is fundamentally a search and retrieval system, built on top of local AI."

---

## Key Points to Emphasize in Q&A

| Question | Answer |
|---|---|
| "Does it use ChatGPT?" | No. All AI runs locally — Whisper for speech, sentence-transformers for embeddings. |
| "What if YouTube blocks transcripts?" | Three-step fallback: captions → yt-dlp subtitles → local Whisper |
| "Can it answer questions?" | No — it retrieves relevant content. It does not generate answers. |
| "Why PostgreSQL and not a vector database?" | pgvector adds vector search to PostgreSQL. One system instead of two. |
| "What languages does it support?" | English and Hindi (the embedding model supports both) |
| "How accurate is Whisper?" | Very accurate for clear educational speech. Language is auto-detected. |
