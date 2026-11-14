"""Cosine-similarity retrieval over assistant_chunks (numpy, in memory)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import store
from .ingest import QUERY_PREFIX
from .llm import embed
from .settings import setting


@dataclass
class Hit:
    id: str
    source_id: str
    title: str
    url: str | None
    text: str
    score: float


def top_k(query_vec: list[float], chunks: list[dict], k: int) -> list[Hit]:
    # skip vectors from a different embed model (size mismatch) instead of failing
    chunks = [c for c in chunks if len(c["embedding"]) == len(query_vec)]
    if not chunks:
        return []
    m = np.asarray([c["embedding"] for c in chunks], dtype=np.float32)
    q = np.asarray(query_vec, dtype=np.float32)
    denom = np.linalg.norm(m, axis=1) * (np.linalg.norm(q) or 1.0)
    scores = (m @ q) / np.where(denom == 0, 1.0, denom)
    order = np.argsort(-scores)[:k]
    return [Hit(chunks[i]["id"], chunks[i]["source_id"], chunks[i]["title"], chunks[i]["url"],
                chunks[i]["text"], float(scores[i])) for i in order]


def retrieve(question: str, k: int | None = None) -> list[Hit]:
    """Top-k reference chunks for the question. Raises OllamaError if the query can't be embedded."""
    chunks = store.all_chunks()
    if not chunks:
        return []
    [qvec] = embed([QUERY_PREFIX + question], timeout=10.0)
    return top_k(qvec, chunks, int(k or setting("assistant_top_k")))
