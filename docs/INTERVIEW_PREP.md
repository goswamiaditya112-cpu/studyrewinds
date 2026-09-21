# StudyRewind — Interview Preparation

## Quick Project Summary (memorize this)

> StudyRewind is a full-stack web application that ingests YouTube lecture playlists and PDF study notes, extracts and transcribes their content using local AI, stores everything in a vector database, and lets students search using natural language to find exactly the right lecture moment or PDF page.

---

## Q&A — What the Project Is

**Q: What problem does StudyRewind solve?**

A: Students studying from YouTube lecture playlists waste time scrubbing through hours of video to find a specific concept. If you remember that a topic was explained somewhere in a 20-hour playlist but don't know which video or timestamp, finding it is painful. StudyRewind solves this by automatically transcribing all the videos, breaking transcripts into chunks, converting them to semantic vectors, and allowing natural language search. You can type "what is deadlock?" and get back the exact video and timestamp where it was explained.

---

**Q: Why did you build this?**

A: I study from a lot of Indian engineering YouTube channels like Gate Smashers, which have hundreds of lectures. I found it impossible to revisit specific concepts efficiently. I wanted a tool that would let me search through all my study material — both video transcripts and PDF notes — using the same search box. I also wanted to build something that uses AI without relying on paid APIs, because I don't have access to cloud AI credits.

---

## Q&A — Technology Choices

**Q: Why React?**

A: React is the most widely used frontend framework for single-page applications. With TypeScript it provides type safety that catches errors at compile time. Vite makes the build fast. It was a natural choice for building a responsive, state-driven UI where the page updates without full reloads.

---

**Q: Why FastAPI?**

A: FastAPI automatically generates OpenAPI documentation, integrates natively with Pydantic for request validation, and uses Python type hints throughout. It is much faster to develop with than Django for a REST API project. It also supports both synchronous and asynchronous route handlers.

---

**Q: Why PostgreSQL?**

A: PostgreSQL is reliable, well-documented, and widely used. More importantly for this project, the pgvector extension adds native vector storage and cosine similarity search directly to PostgreSQL. This means I only need one database system — no separate vector database.

---

**Q: Why pgvector instead of a dedicated vector database like Pinecone or Weaviate?**

A: Two reasons. First, I can keep everything in one database, which simplifies the setup significantly. Relational queries (ownership checks, filtering by subject) and vector searches run in the same query context. Second, at the scale of this project — thousands of chunks, not millions — PostgreSQL with pgvector performs well without needing a dedicated service.

---

**Q: Why local embeddings instead of OpenAI embeddings?**

A: Three reasons: cost, privacy, and offline capability. Using a local sentence-transformers model means zero API cost per embedding, no data being sent to external servers, and the ability to run completely offline after the model is downloaded once. The model I chose — `paraphrase-multilingual-MiniLM-L12-v2` — supports both Hindi and English, which is important for Indian educational content.

---

**Q: Why faster-whisper locally instead of a cloud transcription service?**

A: The same reasons as local embeddings — cost and independence. Cloud transcription services like OpenAI Whisper API charge per minute of audio. A 140-video playlist might cost $12-15 just for transcription. Running Whisper locally is free after the initial model download. The tradeoff is speed: about 1 minute of CPU time per 7 minutes of audio on a laptop, versus near-instant cloud processing.

---

## Q&A — How It Works

**Q: How does YouTube transcript extraction work?**

A: It's a three-step pipeline with fallbacks:

Step 1 is `youtube-transcript-api`, which reads the free caption files that YouTube provides for most videos. This takes about 2 seconds. It fails when YouTube rate-limits the IP address.

Step 2 is yt-dlp subtitle download. yt-dlp mimics a real browser, so it can download the subtitle text file even when Step 1 is rate-limited. This downloads a 30-100 KB text file and takes 3-5 seconds.

Step 3 is local faster-whisper. When both text-based methods fail, yt-dlp downloads the audio track of the video and faster-whisper transcribes it locally. This takes about 1 minute per 7 minutes of audio. This step always works because it doesn't contact YouTube's caption servers at all.

---

**Q: How are timestamps preserved?**

A: The raw transcript output — whether from YouTube captions or Whisper — contains start time and duration for each snippet. When chunking, these timestamps are kept: each chunk stores the `start_time` and `end_time` of the first and last snippets it contains. So every chunk in the database maps exactly back to a position in the video.

---

**Q: How does PDF processing work?**

A: PDF files are uploaded through the API, stored on disk, and processed using the pypdf library. pypdf extracts the text content from each page. Each page's text (or portion of a page if it's very long) becomes a `DocumentChunk` with a `page_number` stored. Embeddings are generated for each chunk, and they go into the `document_chunks` table. Search results from PDFs include the page number so the student knows where to look.

---

**Q: What is a 384-dimensional embedding?**

A: An embedding is a way of representing text as a list of numbers that captures its meaning. The model I'm using outputs 384 numbers for each piece of text. The key property is that texts with similar meanings produce vectors that point in similar directions in 384-dimensional space. "Deadlock in OS" and "circular wait condition" would produce vectors that are close together, even though they don't share any words. This closeness is measured using cosine similarity.

---

**Q: How does vector similarity search work?**

A: Cosine similarity measures the angle between two vectors. A smaller angle means more similar direction means more similar meaning. pgvector uses the `<=>` operator to calculate cosine distance. When you submit a query, it's embedded into a 384-d vector, and the database finds the stored chunk vectors that have the smallest cosine distance from the query vector. These are the most semantically relevant chunks.

---

**Q: How is user data isolated?**

A: Every resource in the database has an owner through a chain: User → Subject → Playlist → Video → TranscriptChunk, and User → Subject → Document → DocumentChunk. Every API endpoint that accesses data first verifies that the resource's owner matches the authenticated user. If a user tries to access someone else's data, they get a 404 Not Found — not a 403, which would confirm the resource exists.

---

**Q: How is IDOR prevented?**

A: IDOR stands for Insecure Direct Object Reference. It's when an attacker guesses a resource ID and accesses data that isn't theirs. I prevent it in two ways. First, all IDs are randomly generated UUIDs — they can't be guessed or enumerated. Second, every request checks ownership before returning data. A valid UUID belonging to another user returns 404.

---

**Q: How does the system handle failures?**

A: Each stage of the pipeline handles failures gracefully. If youtube-transcript-api fails, it logs the failure and tries yt-dlp subtitles. If that fails, it tries Whisper. If all three fail, the video status is set to "failed" with an error message — the application continues working for other videos. The temp audio file cleanup uses a 3-attempt retry with a 0.5-second delay between attempts, to handle Windows file-locking issues.

---

**Q: What are the current limitations?**

A: The main limitations are:
1. YouTube IP blocking can prevent caption and subtitle retrieval, forcing the slower Whisper fallback
2. Whisper on CPU is slow — about 1 minute per 7 minutes of video
3. Processing is synchronous — the browser waits for each video to complete
4. Only public YouTube videos are supported
5. The setup is local-only; production deployment needs additional work
6. No generative AI — the system retrieves relevant content but does not answer questions

---

**Q: Why did you avoid paid APIs?**

A: Practical reasons: cost and availability. As a student I don't have reliable access to cloud AI API credits. I also wanted the project to work entirely offline once set up — no dependency on external services that could change pricing, go down, or block access. The local-first approach also means user data never leaves the machine, which is a privacy benefit.

---

**Q: Why is this not a RAG (Retrieval-Augmented Generation) system?**

A: RAG means using retrieved content to augment the prompt of a generative language model, which then generates a new answer. StudyRewind retrieves content but does not have a generative model. When you search, you get back the actual transcript text and PDF excerpts with timestamps and page numbers — not an AI-generated summary or answer. It is a retrieval system, not a generation system. Adding a generative model on top would be possible as a future extension.

---

**Q: What would you add in the future?**

A: Several things come to mind:
1. Async transcript processing with a task queue (Celery + Redis) so large playlists don't block the browser
2. An LLM layer on top for question answering using retrieved chunks as context
3. Production deployment with HTTPS, proper authentication cookies, and environment management
4. Support for more content types (audio files, other video platforms)
5. Better multilingual support for other Indian languages

---

## Common Viva Questions

**Q: Explain the embedding model you used.**

A: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` is a transformer model fine-tuned for semantic similarity. "Multilingual" means it was trained on text in 50+ languages. "MiniLM" means it's a smaller, distilled version of a larger model. "L12" means it has 12 transformer layers. "384" is the output embedding dimension. It produces normalized unit vectors, which is important because cosine similarity is equivalent to dot product for unit vectors.

---

**Q: What is pgvector?**

A: pgvector is an open-source extension for PostgreSQL that adds a `vector` data type and similarity search operators. The `<=>` operator computes cosine distance. It integrates with PostgreSQL's existing query planner, so you can combine vector search with relational filters in the same query — for example, "find nearest vectors WHERE subject belongs to current user."

---

**Q: What is Argon2id and why use it?**

A: Argon2id is a password hashing algorithm that won the Password Hashing Competition in 2015. It is memory-hard, meaning it requires a configurable amount of RAM to compute, which makes GPU-based brute-force attacks expensive. The "id" variant combines two versions of Argon2 to be resistant to both side-channel attacks and GPU attacks. OWASP recommends it as the first choice for password hashing.

---

**Q: What is the difference between authentication and authorization?**

A: Authentication is verifying who you are — "prove you are this user" — which is the login + JWT token process. Authorization is verifying what you are allowed to do — "does this user own this resource?" — which is the ownership check at every endpoint. Both are implemented in StudyRewind.
