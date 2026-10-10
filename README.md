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
| Citation highlighting on the real rendered PDF or Word page: multi-line quotes, quotes across a page break, repeated quotes with a next/previous stepper | Done and checked in a real browser |
| Multi-document questions: select several documents, one integrated comparison, each quote names and is verified in its own document | Done and checked in a real browser |
| Version comparison (Part B 7): two versions compared clause by clause, figure changes caught by code, plain-language overview, filter and sort by significance | Done and checked in a real browser |
| Part C, Option 2: research mode where the model calls tools (search, read a section, list clauses) in a bounded loop, shown live, malformed calls handled, quotes still verified | Done and checked in a real browser |

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

### Citation highlighting

Clicking a verified quote opens the original file (rendered with pdf.js for PDFs and docx-preview for
Word) and highlights the passage on the page. The viewer does not reuse the server's character
offsets, because a renderer splits and orders the same words differently. It finds the verified quote
again in the text it rendered, ignoring whitespace, so wrapped lines, odd spacing and split text
spans do not matter. Quotes that cross a page break are highlighted on both pages, and a quote that
appears several times can be stepped through ("2 of 3"). If a quote cannot be placed on the rendered
page, the interface says so and shows it in the extracted text instead. See `decisions.txt` (D15).

### Asking across several documents

Select two to five documents in the library and choose **Ask across N documents**. Each document is searched on its own
(a long contract cannot crowd out a short one), and the relevance judge decides per document whether
its evidence is enough, so only the documents still short are searched again. The answer is a single
comparison rather than one summary per document, a document with nothing relevant is reported as such,
and every quote names its document. Each quote is verified against **only the document it is credited
to**: a sentence that exists in document A but is attributed to document B is shown as unverified. See
`decisions.txt` (D16).

### Comparing two versions of a contract

Select exactly two documents (the first is the older) and choose **See what changed**. Each version is
split into clauses, the clauses are matched by content rather than number, and every pair is checked
for changed figures, dates, periods and obligation words by code, so a liability cap moving from
AED 100,000 to AED 1,000,000 can never be rated as a rewording: a model's rating can be raised by these
rules but never lowered below them. The model then rates the rest, and writes a short overview that
quotes the exact figures. Changes are listed most significant first and can be filtered or sorted; each
shows before and after side by side and opens in the original document. Without an OpenAI key the
comparison still runs and says plainly that ratings are rules-only. See `decisions.txt` (D17).

### Research mode (Part C, Option 2)

Beside the question box, switch from **Standard** to **Research** and the model stops following a fixed
script. It is given three tools, `search_document`, `get_section` and `list_clauses`, and decides what
to look up, reads the result, and decides again: for example finding a liability clause that says
"subject to clause 14" and then reading clause 14. Each call appears as it happens ("Searching for
...", "Reading section 14", "Found 4 passages on pages 3, 4") and stays in the answer's history.

The loop is bounded by code: a hard cap on rounds, a cap on calls per round and a budget for invalid
calls. A tool call with an unknown name, broken JSON, a missing or wrongly typed argument, or invented
parameters never crashes the request: the model is told what was wrong and tries again. The answer is
then written from only what was read, streamed, and every quote is verified against the document as in
Standard mode. Research is available for one document at a time. See `decisions.txt` (D18).

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
| `MAX_DOCUMENTS_PER_QUESTION` | Most documents that can be compared in one question | `5` |
| `CANDIDATES_PER_DOCUMENT` | Passages judged per document in each round of a comparison | `8` |
| `MAX_AI_RATED_CHANGES` | Most changes in one comparison that the model rates (the rest use the rules) | `120` |
| `RATE_BATCH_SIZE` / `RATE_CONCURRENCY` | Changes per rating call, and how many calls run at once | `6` / `4` |
| `MAX_RESEARCH_ROUNDS` | Hard cap on tool-calling rounds in research mode | `6` |
| `MAX_TOOL_CALLS_PER_ROUND` / `MAX_INVALID_TOOL_CALLS` | Calls run per model turn, and bad calls tolerated before the loop stops | `4` / `4` |
| `RESEARCH_MAX_EVIDENCE` / `RESEARCH_PASSAGE_CHARS` / `RESEARCH_SECTION_CHARS` | Passages kept for the answer, and the size limits of a search result and of a section read | `14` / `900` / `4000` |
| `NEIGHBOR_CHUNKS` | Surrounding chunks added around a strong passage (`0` turns off) | `1` |
| `CHAT_MEMORY_TURNS` | Earlier question/answer exchanges the assistant remembers (`0` turns memory off, max `20`) | `6` |
| `CHAT_MEMORY_CHARS` | Earlier answers are shortened to this length before the model sees them | `800` |
| `MAX_UPLOAD_MB` | Largest accepted upload | `25` |
| `CORS_ORIGINS` | Allowed browser origins | `http://localhost:3000` |

## Project layout

```
Backend/   FastAPI service
  app/extraction.py     PDF/DOCX text extraction (LangChain loaders)
  app/rag/              chunking, hybrid index, LLM client, agent loop, quote verification (quotes.py)
  app/rag/research_*.py  research mode: tool definitions with argument checks, the bounded tool-calling loop
  app/compare/          clause segmentation, alignment, figure extraction, rating, comparison engine
  app/routers/          documents, chat, conversations and comparisons endpoints
  tests/                pytest suite (LLM replaced by a scripted fake)
Frontend/  Next.js (App Router, TypeScript, Tailwind v4)
decisions.txt           design decisions and trade-offs
```
