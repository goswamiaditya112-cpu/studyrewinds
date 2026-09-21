# StudyRewind — AI Pipeline Documentation

## Overview

StudyRewind uses three local AI components to turn raw educational content into a searchable knowledge base. None of these components require a paid API key, an internet connection during inference, or cloud services.

```
YouTube Video / PDF
        │
        ▼
  Content Extraction  ──── YouTube: 3-step transcript pipeline
        │              ──── PDF: pypdf page extraction
        ▼
  Text Chunking       ──── 60–90s windows (video) / page-aware (PDF)
        │
        ▼
  Local Embeddings    ──── paraphrase-multilingual-MiniLM-L12-v2
        │              ──── 384-dimensional normalized vectors
        ▼
  pgvector Storage    ──── PostgreSQL vector(384) columns
        │
        ▼
  Semantic Search     ──── cosine similarity query
```

---

## Part 1 — YouTube Transcript Pipeline

### Purpose
Extract timestamped text from YouTube lecture videos so each 60–90 second section can be embedded and searched.

### Three-Step Pipeline

The pipeline tries three methods in order, using the next only if the previous fails:

---

#### Step 1 — youtube-transcript-api (Fastest: ~2 seconds)

```python
from youtube_transcript_api import YouTubeTranscriptApi
```

YouTube automatically generates captions for most videos and makes them available through a public endpoint. `youtube-transcript-api` reads that endpoint — no official YouTube API key required.

**Language preference order:**
```
hi → hi-Latn → en → en-US → en-GB → en-IN
```
Hindi is preferred first because the target content is Indian educational YouTube lectures.

**Failure modes:**
- `IpBlocked` / `RequestBlocked` — YouTube rate-limits networks that make too many automated requests
- `TranscriptsDisabled` — creator has disabled captions
- `NoTranscriptFound` — no captions in supported languages

When this step fails, the error is caught silently and the pipeline moves to Step 2.

---

#### Step 2 — yt-dlp Subtitle Download (Fast: ~3–5 seconds)

```python
import yt_dlp
ydl_opts = {
    "writeautomaticsub": True,
    "skip_download": True,   # downloads only the .vtt text file, not audio
    "subtitlesformat": "vtt",
    ...
}
```

`yt-dlp` mimics a real browser (sends full headers and cookies), so it bypasses the IP-based rate limiting that blocks `youtube-transcript-api`. It downloads only the subtitle text file (~30–100 KB), not the audio or video.

**VTT parsing:** YouTube's `.vtt` files use a rolling-window format where the same text appears in multiple consecutive cues. The parser deduplicates these by keeping the last version of each `(start, end)` timestamp pair, then removes consecutive identical texts.

**Language preference:**
```
hi → hi-IN → en-IN → en
```

**Failure mode:** If subtitles do not exist on the video (disabled) or YouTube blocks this endpoint too, the pipeline moves to Step 3.

---

#### Step 3 — faster-whisper Local Transcription (Reliable fallback: ~1–2 min)

```python
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=<half_cores>)
segments, info = model.transcribe(audio_path, beam_size=2)
```

When text-based methods fail, the pipeline:
1. Uses `yt-dlp` to download only the audio track (`.m4a` file, ~10–18 MB)
2. Runs faster-whisper on the audio locally
3. Deletes the audio file immediately after transcription

**Model specifications:**
- Model: `base` (74M parameters)
- Quantization: `int8` (reduces memory and compute requirements)
- Device: `cpu` (no GPU required)
- CPU threads: half of available cores (to prevent full CPU saturation and thermal throttling on laptops)
- Beam size: 2 (reduced from 5 to lower CPU load; negligible quality difference for clear speech)

**Speed benchmark (measured):**
- 7-minute video → ~57 seconds on a cool laptop CPU
- 13-minute video → ~134 seconds
- 19-minute video → ~126 seconds

**Language detection:** Whisper automatically detects the language. Hindi was detected at 0.97–0.98 probability in testing.

**Cleanup:** The temporary audio directory is deleted after transcription with a 3-attempt retry (to handle Windows file-locking). If cleanup fails after 3 attempts, a warning is logged.

---

### Chunking

Raw transcript output (individual 2–5 second snippets) is grouped into 60–90 second windows:

```
Input:  [0-3s "Hello"] [3-6s "friends"] [6-9s "welcome"] ...
                        ↓
Output: Chunk 1: [0s–64s] "Hello friends welcome to Gate Smashers today's topic is..."
        Chunk 2: [64s–128s] "...the first concept we need to understand..."
```

Each chunk stores: `start_time`, `end_time`, `text`, `embedding`.

This window size is chosen to be:
- Small enough to return specific, focused results
- Large enough to contain meaningful context for semantic matching

---

## Part 2 — PDF Processing Pipeline

### Purpose
Extract text from uploaded PDF study notes and textbook chapters, chunk it by page, and make it searchable alongside YouTube transcripts.

### How It Works

```
PDF upload (multipart/form-data)
        │
        ▼
pypdf extracts text page by page
        │
        ▼
Each page's text is further chunked if long
(page_number and chunk_index are preserved)
        │
        ▼
DocumentChunk records created in database
        │
        ▼
Embedding generated for each chunk
        │
        ▼
Stored in document_chunks with vector(384) column
```

**Provenance:** Every DocumentChunk stores its `page_number`, so search results can tell the student exactly which page to open.

---

## Part 3 — Local Embedding Generation

### Model

```
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

**Key properties:**
- Multilingual: supports 50+ languages including English and Hindi
- Output: 384-dimensional normalized unit vectors
- Size: ~118 MB (downloaded once, cached locally)
- Device: CPU (no GPU required)
- Inference: ~32 texts/batch, deterministic output

### Why This Model?

| Property | Value |
|---|---|
| Supports Hindi + English | Yes |
| Free to use | Yes |
| Runs without internet | Yes (after first download) |
| Output dimension | 384 (matches pgvector schema) |
| Normalized output | Yes (enables cosine similarity) |

### Singleton Pattern

The model is loaded once at first request and kept in memory:

```python
_embedding_model = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _embedding_model
```

This avoids re-loading the 118 MB model weights on every request.

### Output Validation

Every generated vector is validated:
- Exactly 384 dimensions
- All values are finite (no NaN or Infinity)
- L2 norm ≈ 1.0 (unit vector, required for cosine similarity)

---

## Part 4 — pgvector Storage

### Schema

Both chunk types have a `vector(384)` column:

```python
# transcript_chunks table
embedding = mapped_column(Vector(384), nullable=False, default=lambda: [0.0] * 384)

# document_chunks table
embedding = mapped_column(Vector(384), nullable=False, default=lambda: [0.0] * 384)
```

The default `[0.0] * 384` (zero vector) has L2 norm = 0, which is used to detect un-embedded chunks.

### Idempotency

The storage service checks whether a chunk already has a valid embedding before generating a new one:

```python
def is_valid_embedding(embedding):
    norm = sum(x * x for x in embedding)
    return norm > 0.01  # zero vector (un-embedded) has norm = 0
```

This makes the embedding step safe to re-run without duplicating work.

### Batch Processing

Chunks are embedded in batches of 32 for efficiency:

```python
vectors = service.embed_texts(texts, batch_size=32)
```

---

## Part 5 — Semantic Search

### How a Search Query Is Processed

```
User query: "what causes deadlock?"
        │
        ▼
embed_text(query) → 384-d normalized vector
        │
        ▼
SELECT ... FROM transcript_chunks tc
JOIN videos v ON tc.video_id = v.id
JOIN playlists p ON v.playlist_id = p.id
JOIN subjects s ON p.subject_id = s.id
WHERE s.user_id = <current_user>
  AND s.id = <subject_id>
ORDER BY tc.embedding <=> <query_vector>  -- cosine distance
LIMIT top_k
        │
        ▼
Same search on document_chunks
        │
        ▼
Merge + rank combined results
        │
        ▼
Return with provenance:
  - YouTube: video title, youtube_video_id, start_time, end_time, chunk text
  - PDF: document filename, page_number, chunk_index, chunk text
```

### Cosine Distance Operator

pgvector uses the `<=>` operator for cosine distance:

```sql
ORDER BY embedding <=> '[0.1, 0.3, ...]'::vector
```

A cosine distance of `0` means identical direction (perfect match). A distance of `1` means opposite. Results are sorted ascending (smallest distance = most relevant).

### Why Semantic Search vs. Keyword Search?

| | Keyword Search | Semantic Search |
|---|---|---|
| Query: "process scheduling" | Finds documents containing exactly those words | Also finds "CPU scheduling", "round robin", "context switching" |
| Query: "डेडलॉक क्या है" (Hindi) | Requires Hindi keywords in document | Can match English content about deadlock |
| Finds synonyms | No | Yes |
| Finds related concepts | No | Yes |

Semantic search matches by meaning rather than exact text, which is significantly more useful for studying where you remember concepts but not exact terminology.

---

## Summary — What Is AI and What Is Not

| Component | Is it AI? | What it actually does |
|---|---|---|
| faster-whisper | ✅ AI (speech recognition model) | Converts audio to text |
| sentence-transformers | ✅ AI (language model) | Converts text to vectors |
| pgvector cosine search | ❌ Not AI (math) | Finds nearest vectors |
| youtube-transcript-api | ❌ Not AI (HTTP client) | Reads YouTube captions |
| yt-dlp | ❌ Not AI (downloader) | Downloads audio/subtitles |
| pypdf | ❌ Not AI (parser) | Extracts text from PDFs |

StudyRewind does **not** use a generative AI model (LLM). It does not generate answers — it retrieves and surfaces relevant content from material the student has already uploaded. This is a retrieval system, not a generative system.
