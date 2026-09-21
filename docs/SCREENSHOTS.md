# StudyRewind — Screenshots Guide

## Purpose

This document lists the important screens in StudyRewind and describes what each one shows. Use this guide when taking screenshots for GitHub, a project report, or a portfolio.

---

## Important Screens to Capture

### 1. Login / Landing Page
**URL:** `http://localhost:5173` (when not logged in)

**What to show:**
- StudyRewind logo and application name
- Email and password input fields
- Login button
- Link to register a new account

**Why it matters:** First impression of the application.

---

### 2. Registration Page
**URL:** `http://localhost:5173` → click Register

**What to show:**
- Registration form with email and password fields
- Submit button

---

### 3. Dashboard / Subject List
**URL:** `http://localhost:5173` → after login

**What to show:**
- List of subjects (e.g., DBMS, Operating Systems)
- "Create Subject" button
- Subject cards with basic info

**Why it matters:** Shows the organizational structure of the application.

---

### 4. Subject Workspace
**URL:** Click on any subject from dashboard

**What to show:**
- Subject name and description
- List of YouTube playlists imported into this subject
- List of PDF documents uploaded to this subject
- "Add Playlist" and "Upload PDF" buttons
- Search bar for semantic search

**Why it matters:** Shows the core organizational unit and entry point to all features.

---

### 5. Add YouTube Playlist
**URL:** Click "Add Playlist" from subject workspace

**What to show:**
- Playlist URL input field
- Subject dropdown
- "Analyze Playlist" button

**Tip:** Paste a real playlist URL to show the form populated.

---

### 6. Playlist Video List
**URL:** Click on a playlist from subject workspace

**What to show:**
- List of videos in the playlist
- Each video's title, duration, and transcript status badge:
  - **Available** (green) — transcript processed
  - **Processing** (yellow/spinner) — currently processing
  - **Queued/Pending** (grey) — waiting to be processed
  - **Unavailable** (red) — failed
- "Retrieve" button on individual videos

**Why it matters:** Shows the transcript processing workflow and status tracking.

---

### 7. Transcript Processing in Progress
**URL:** Click "Retrieve" on a Pending video

**What to show:**
- Video transitioning to "Processing" status
- If possible, show it completing and switching to "Available"

**Why it matters:** Demonstrates the live transcript extraction pipeline.

---

### 8. Transcript View
**URL:** Click on an "Available" video → View Transcript

**What to show:**
- List of transcript chunks
- Each chunk showing start time, end time, and text
- Clickable timestamps that open YouTube at that moment

**Why it matters:** Shows the core output of the transcription pipeline with timestamp provenance.

---

### 9. Search Interface
**URL:** Subject workspace → Search section

**What to show:**
- Natural language search input (e.g., "what is deadlock?")
- Top-K results slider or default
- Search button

**Why it matters:** Entry point to the semantic search feature.

---

### 10. Search Results
**URL:** After submitting a search query

**What to show:**
- List of results with relevance scores
- YouTube transcript results showing:
  - Video title
  - Timestamp (start time – end time)
  - Relevant text snippet
  - Link/button to open video at timestamp
- PDF document results showing:
  - Document name
  - Page number
  - Relevant text snippet

**Why it matters:** This is the core feature — shows semantic search working with provenance.

---

### 11. PDF Study Materials Section
**URL:** Subject workspace → Study Materials

**What to show:**
- List of uploaded PDFs
- Each document showing filename, page count, status
- "Upload PDF" button

---

### 12. Health Check (API)
**URL:** `http://localhost:8000/health/db` (in browser or Swagger UI)

**What to show:**
```json
{
  "status": "healthy",
  "database": "postgresql",
  "pgvector_installed": true,
  "pgvector_version": "0.8.0",
  "pg_version": "PostgreSQL 16.x..."
}
```

**Why it matters:** Proves the backend and pgvector are running correctly.

---

### 13. Swagger API Documentation
**URL:** `http://localhost:8000/docs`

**What to show:**
- Full list of API endpoints with their descriptions
- Interactive test interface

**Why it matters:** Shows the API is well-structured and documented.

---

## Screenshot Tips

1. **Use a clean browser** — close other tabs, use incognito if needed
2. **Use realistic data** — real playlist titles and video names look more professional than "Test Subject 1"
3. **Show the happy path** — screenshots with "Available" transcripts and actual search results
4. **Capture search results** — this is the most important screenshot; it proves the whole system works end-to-end
5. **Include timestamps** — showing `[123.4s – 187.2s]` in transcript chunks proves timestamp preservation

---

## Recommended Screenshot Order for a Project Report

1. Login page
2. Dashboard with subjects
3. Subject workspace (DBMS with playlist)
4. Playlist with video list and status badges
5. Transcript view with chunks and timestamps
6. Search input with a natural language question
7. Search results with video timestamp provenance
8. Health check confirming pgvector

This sequence tells the complete story from login to working semantic search.
