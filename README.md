# Marginalia

A web app for analysing legal contracts. Upload a PDF or DOCX, ask questions in a chat, and get
answers that are backed by quotes the app has **checked against the document itself**.

The design goal is accuracy over speed. A contract answer that is fast and wrong is worse than a
slow answer that can be verified, so the chat is built around retrieval that is graded before it is
trusted, and quotes that are verified by code before they are shown.

> Full reasoning for every design choice is in [`decisions.txt`](./decisions.txt).

## Status

| Area | State |
| --- | --- |
| Upload PDF/DOCX, type validation, live progress, empty/scanned detection, document library | Done |
| Chat with a document: agentic RAG, streaming, stop and keep partial answer, saved history | Done (needs an OpenAI key, see below) |
| Verified quotes (whitespace-tolerant, cross-page, never trusts model positions) | Done |
| Open a citation in the document at the right page with the quote highlighted | Basic version done |
| Multi-document questions, document comparison, Part C | Not started |

## How the chat answers a question (agentic RAG)

```
question
   |
   v
1. Query generation   LLM turns the question + recent chat into 1-3 contract-style search queries
                      and rewrites follow-ups ("what does it cover?") into a standalone question
   |
   v
2. Retrieval          hybrid search: stemmed BM25 + embeddings, both aware of each chunk's section
                      heading, fused with RRF. The whole question is searched as well as the queries
   |
   v
3. Quality grading    LLM judge scores every passage 0/1/2 and decides: is this SUFFICIENT?
   |   no, and rounds remain (max 3)
   +--------------------> refine queries using what was missing, retrieve again
   |   yes
   v
4. Augment            only passages the judge accepted, plus the text around the strong ones,
                      go into the answer prompt
   |
   v
5. Generate           streamed answer with numbered citations and verbatim quotes, plus an optional
                      clearly labelled general explanation (never counted as the document)
   |
   v
6. Verify             our code finds each quote in the real text; unfound quotes are flagged
```

If retrieval never becomes good enough, the app does not guess. It reports that no supporting
passage was found, says what it searched, and notes any pages it could not read. It never claims a
clause does not exist, only that none was found.

### Quote verification

Quotes are matched against the stored page text after normalising both sides: whitespace and line
breaks, curly quotes and dashes, ligatures, case, and words hyphenated across a line break. Matching
runs over the whole document joined across pages, so quotes that span a page break are found, and
results are mapped back to original character offsets. Positions reported by the model are ignored.
See `decisions.txt` (D8) for where this can fail.

## Run locally

Requirements: Python 3.13, Node 20+.

**Backend**

```powershell
cd Backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env        # then add your OPENAI_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

**Frontend** (second terminal)

```powershell
cd Frontend
npm install
copy .env.example .env
npm run dev
```

Open http://localhost:3000. The API docs are at http://localhost:8000/docs.

**Tests**

```powershell
cd Backend
.\.venv\Scripts\python.exe -m pytest -q
```

### Configuration (`Backend/.env`)

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Key for the LLM and embeddings. Never commit it. | none |
| `OPENAI_BASE_URL` | Any OpenAI-compatible endpoint | OpenAI |
| `OPENAI_MODEL` | Chat model | `gpt-4o-mini` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `MAX_RETRIEVAL_ROUNDS` | Cap on search-grade-refine rounds | `3` |
| `TEMPERATURE_PLAN` / `TEMPERATURE_JUDGE` / `TEMPERATURE_ANSWER` | Sampling temperature for query writing, relevance judging and answering | `0.3` / `0.1` / `0.4` |
| `CANDIDATES_PER_ROUND` | Passages judged in each search round | `14` |
| `MAX_EVIDENCE_PASSAGES` | Passages the answer may be written from | `10` |
| `NEIGHBOR_CHUNKS` | Surrounding chunks added around a strong passage (`0` turns off) | `1` |
| `CHAT_MEMORY_TURNS` | Earlier question/answer exchanges the assistant remembers (`0` turns memory off, max `20`) | `6` |
| `CHAT_MEMORY_CHARS` | Earlier answers are shortened to this length before the model sees them | `800` |
| `MAX_UPLOAD_MB` | Largest accepted upload | `25` |
| `CORS_ORIGINS` | Allowed browser origins | `http://localhost:3000` |

## Project layout

```
Backend/   FastAPI service
  app/extraction.py     PDF/DOCX text extraction (LangChain loaders)
  app/rag/              chunking, hybrid index, LLM client, agent loop, quote verification
  app/routers/          documents and chat endpoints
  tests/                pytest suite (LLM replaced by a scripted fake)
Frontend/  Next.js (App Router, TypeScript, Tailwind v4)
decisions.txt           design decisions and trade-offs
```
