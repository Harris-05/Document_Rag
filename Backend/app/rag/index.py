"""Hybrid retrieval over one document's chunks.

BM25 catches exact legal terms, numbers and defined terms that embeddings blur together.
Embeddings catch paraphrase ("walk away" vs "terminate"). The two rankings are merged with
Reciprocal Rank Fusion, which needs no score calibration between them.
"""

import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import snowballstemmer
from rank_bm25 import BM25Plus

from app.db import connect
from app.rag.chunking import RawChunk, chunk_pages
from app.rag.llm import LLMClient, LLMError

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
_RRF_K = 60
_DEPTH = 30
_STEMMER = snowballstemmer.stemmer("english")
# Words that appear in nearly every clause and carry no signal for keyword search.
_STOPWORDS = frozenset(
    "a an and are as at be been being but by can could did do does for from had has have how i if in into is it "
    "its may me my no not of on or our shall should so such than that the their them then there these they this "
    "those to under upon us was we were what when where which who whom whose why will with within would you your".split()
)


@dataclass(frozen=True)
class Chunk:
    id: int
    ordinal: int
    page_number: int
    text: str
    context: str = ""

    @property
    def search_text(self) -> str:
        """What is matched and embedded: the section heading plus the clause text."""
        return self.context + "\n" + self.text if self.context else self.text


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    via: str  # "keyword", "semantic" or "both"


@lru_cache(maxsize=50_000)
def _stem(word: str) -> str:
    # Very short words are left alone: stemming turns currency codes like "aed" into "a".
    return _STEMMER.stemWord(word) if len(word) >= 4 else word


def tokenize(text: str) -> list[str]:
    """Lower-case, drop filler words, and reduce words to their stem.

    Stemming is what lets a search for "terminate" find "termination" and "terminated".
    Numbers are kept as written.
    """
    return [
        token if token[0].isdigit() else _stem(token)
        for token in _TOKEN.findall(text.lower())
        if token not in _STOPWORDS
    ]


def _vector_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def load_chunks(document_id: str) -> list[tuple[Chunk, bytes | None]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, ordinal, page_number, text, context, embedding FROM chunks WHERE document_id = ? ORDER BY ordinal",
            (document_id,),
        ).fetchall()
    return [(Chunk(r["id"], r["ordinal"], r["page_number"], r["text"], r["context"]), r["embedding"]) for r in rows]


def store_chunks(document_id: str, chunks: list[RawChunk]) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        connection.executemany(
            "INSERT INTO chunks (document_id, ordinal, page_number, text, context) VALUES (?, ?, ?, ?, ?)",
            [(document_id, i, c.page_number, c.text, c.context) for i, c in enumerate(chunks)],
        )


def store_embeddings(connection: sqlite3.Connection, pairs: list[tuple[int, bytes]]) -> None:
    connection.executemany("UPDATE chunks SET embedding = ? WHERE id = ?", [(blob, cid) for cid, blob in pairs])


class DocumentIndex:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray | None) -> None:
        self.chunks = chunks
        self._vectors = vectors
        tokenized = [tokenize(c.search_text) or ["_"] for c in chunks]
        self._token_sets = [set(tokens) for tokens in tokenized]
        # BM25Plus (unlike BM25Okapi) never gives a term a zero or negative weight, which matters
        # for short contracts where a term often appears in half the chunks or more.
        self._bm25 = BM25Plus(tokenized) if chunks else None

    @property
    def has_embeddings(self) -> bool:
        return self._vectors is not None

    def search(self, queries: list[str], query_vectors: list[list[float]] | None, k: int) -> list[Hit]:
        if not self.chunks or self._bm25 is None:
            return []

        fused: dict[int, float] = {}
        sources: dict[int, set[str]] = {}

        def credit(position: int, rank: int, source: str) -> None:
            fused[position] = fused.get(position, 0.0) + 1.0 / (_RRF_K + rank)
            sources.setdefault(position, set()).add(source)

        for query in queries:
            tokens = tokenize(query)
            if tokens:
                wanted = set(tokens)
                scores = self._bm25.get_scores(tokens)
                matching = [i for i in np.argsort(-scores) if self._token_sets[i] & wanted]
                for rank, position in enumerate(matching[:_DEPTH], start=1):
                    credit(int(position), rank, "keyword")

        if self._vectors is not None and query_vectors:
            for vector in query_vectors:
                query_vec = np.asarray(vector, dtype=np.float32)
                norm = np.linalg.norm(query_vec)
                if norm == 0:
                    continue
                similarity = self._vectors @ (query_vec / norm)
                for rank, position in enumerate(np.argsort(-similarity)[:_DEPTH], start=1):
                    credit(int(position), rank, "semantic")

        ordered = sorted(fused, key=lambda position: fused[position], reverse=True)[:k]

        # A document smaller than the candidate window is simply handed over whole: ranking adds
        # nothing, and the judge can read every part of it.
        if len(self.chunks) <= k:
            rest = [position for position in range(len(self.chunks)) if position not in fused]
            return [
                Hit(
                    chunk=self.chunks[position],
                    score=fused.get(position, 0.0),
                    via=("both" if len(sources[position]) == 2 else next(iter(sources[position])))
                    if position in sources
                    else "whole document",
                )
                for position in [*ordered, *rest]
            ]

        return [
            Hit(
                chunk=self.chunks[position],
                score=fused[position],
                via="both" if len(sources[position]) == 2 else next(iter(sources[position])),
            )
            for position in ordered
        ]


@dataclass(frozen=True)
class IndexBuild:
    index: DocumentIndex
    freshly_built: bool
    embeddings_ok: bool
    embedding_error: str | None = None


async def ensure_index(
    document_id: str, pages: list[tuple[int, str]], llm: LLMClient, target: int, overlap: int
) -> IndexBuild:
    """Load the cached index, building and embedding the chunks first if this is the first use."""
    stored = load_chunks(document_id)
    freshly_built = not stored
    if freshly_built:
        store_chunks(document_id, chunk_pages(pages, target, overlap))
        stored = load_chunks(document_id)

    chunks = [chunk for chunk, _ in stored]
    missing = [(chunk, blob) for chunk, blob in stored if blob is None]
    embedding_error: str | None = None

    if missing and chunks:
        try:
            vectors = await llm.embed([chunk.search_text for chunk, _ in missing])
            with connect() as connection:
                store_embeddings(
                    connection, [(chunk.id, _vector_blob(v)) for (chunk, _), v in zip(missing, vectors, strict=True)]
                )
            stored = load_chunks(document_id)
        except LLMError as error:
            embedding_error = error.message

    blobs = [blob for _, blob in stored]
    if chunks and all(blob is not None for blob in blobs):
        matrix = np.vstack([np.frombuffer(blob, dtype=np.float32) for blob in blobs])  # type: ignore[arg-type]
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return IndexBuild(DocumentIndex(chunks, matrix / norms), freshly_built, True)
    return IndexBuild(DocumentIndex(chunks, None), freshly_built, False, embedding_error)


def has_chunks(document_id: str) -> bool:
    with connect() as connection:
        row = connection.execute("SELECT 1 FROM chunks WHERE document_id = ? LIMIT 1", (document_id,)).fetchone()
    return row is not None
