# StudyRewind — Project Startup Quick Reference

Use this one-page guide every time you want to turn on and run your project.

---

## Prerequisites (Start Database)

Open any PowerShell window and run:

```powershell
docker start backend-postgres-1
```
> **What it does:** Starts your PostgreSQL container with the `pgvector` extension so the database is online.

---

## Terminal 1: Backend Server (FastAPI)

Open your first PowerShell window and run these three commands in order:

```powershell
cd "C:\Users\goswa\OneDrive\Desktop\PROJECT\STD RAG\studyrewinds"
```
> **What it does:** Navigates to your project root folder where the Python virtual environment (`venv`) is located.

```powershell
$env:PYTHONPATH="backend"
```
> **What it does:** Tells Python where to find the application code packages inside the `backend` folder.

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```
> **What it does:** Starts the FastAPI backend server on `http://localhost:8000` to handle APIs, transcripts, and AI searches.

*(Keep this terminal open while using the project)*

---

## Terminal 2: Frontend App (React + Vite)

Open a second PowerShell window and run these two commands in order:

```powershell
cd "C:\Users\goswa\OneDrive\Desktop\PROJECT\STD RAG\studyrewinds\frontend"
```
> **What it does:** Navigates into the frontend folder containing your React and TypeScript application.

```powershell
npm run dev
```
> **What it does:** Launches the Vite local web server to serve your user interface at `http://localhost:5173`.

*(Keep this terminal open while using the project)*

---

## Open and Log In

1. Open your browser and go to: **`http://localhost:5173`**
2. Log in with your credentials:
   - **Email:** `alex.student@college.edu`
   - **Password:** `StudyRewind2025!`

---

## Quick Testing Command (Optional)

In project root (`studyrewinds`), run:
```powershell
.\venv\Scripts\python.exe -m pytest backend/tests -q
```
> **What it does:** Runs the automated test suite to verify all 184 backend features are working properly.
