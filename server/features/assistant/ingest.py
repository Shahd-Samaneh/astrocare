"""Index references/*.txt into the assistant_chunks table.

    node scripts/py.mjs -m server.features.assistant.ingest        # (re)index, idempotent
    node scripts/py.mjs -m server.features.assistant.ingest --dry  # show chunks, no Ollama

Each file starts with a header (title:, url:, id:) and a blank line. The text is split into
~500-word chunks with a small overlap and embedded with nomic-embed-text via local Ollama.
Idempotent: a chunk whose text + model hash is unchanged is not re-embedded; chunks of
removed files (or past the new end of a shorter file) are deleted.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from server.core import db
from server.core.config import REFERENCES_DIR

from . import store
from .llm import OllamaError, embed
from .settings import ollama_cfg, setting

# nomic-embed-text expects task prefixes for retrieval.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


@dataclass
class RefDoc:
    source_id: str
    title: str
    url: str | None
    body: str


@dataclass
class Chunk:
    id: str
    source_id: str
    title: str
    url: str | None
    chunk_index: int
    text: str


def parse_reference(path: Path) -> RefDoc:
    """Read the `key: value` header up to the first blank line, then the body."""
    raw = path.read_text(encoding="utf-8").lstrip("﻿")
    header: dict[str, str] = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip():
        key, sep, val = lines[i].partition(":")
        if not sep or key.strip().lower() not in {"title", "url", "id"}:
            break  # no (more) header: the body starts here
        header[key.strip().lower()] = val.strip()
        i += 1
    body = "\n".join(lines[i:]).strip()
    return RefDoc(
        source_id=header.get("id") or path.stem,
        title=header.get("title") or path.stem,
        url=header.get("url") or None,
        body=body,
    )


def chunk_words(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(size - overlap, 1)
    out = []
    for start in range(0, len(words), step):
        out.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return out


def build_chunks(ref_dir: Path = REFERENCES_DIR) -> list[Chunk]:
    size, overlap = int(setting("assistant_chunk_words")), int(setting("assistant_chunk_overlap_words"))
    chunks: list[Chunk] = []
    for path in sorted(ref_dir.glob("*.txt")):
        doc = parse_reference(path)
        for i, text in enumerate(chunk_words(doc.body, size, overlap)):
            chunks.append(Chunk(f"{doc.source_id}:{i}", doc.source_id, doc.title, doc.url, i, text))
    return chunks


def _hash(text: str, model: str) -> str:
    return hashlib.sha1(f"{model}\n{text}".encode("utf-8")).hexdigest()


def ingest(ref_dir: Path = REFERENCES_DIR, *, batch: int = 4, verbose: bool = False) -> dict[str, int]:
    store.ensure_tables()
    model = ollama_cfg()["embed_model"]
    chunks = build_chunks(ref_dir)
    with db.connect() as conn:
        existing = {r["id"]: r["content_hash"] for r in conn.execute("SELECT id, content_hash FROM assistant_chunks")}

    todo = [c for c in chunks if existing.get(c.id) != _hash(c.text, model)]
    for start in range(0, len(todo), batch):
        part = todo[start:start + batch]
        # generous timeout: the first call also loads the model (dev-time command, not the app)
        vecs = embed([DOC_PREFIX + c.text for c in part], timeout=300.0)
        if verbose:
            print(f"  embedded {min(start + batch, len(todo))}/{len(todo)}", flush=True)
        with db.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO assistant_chunks (id, source_id, title, url, chunk_index, text,"
                " content_hash, embed_model, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(c.id, c.source_id, c.title, c.url, c.chunk_index, c.text, _hash(c.text, model), model,
                  json.dumps(v)) for c, v in zip(part, vecs)],
            )

    keep = {c.id for c in chunks}
    stale = [cid for cid in existing if cid not in keep]
    with db.connect() as conn:
        conn.executemany("DELETE FROM assistant_chunks WHERE id = ?", [(cid,) for cid in stale])
        # header-only changes (title/url) don't change the hash: keep them in sync too
        conn.executemany(
            "UPDATE assistant_chunks SET title = ?, url = ? WHERE id = ?",
            [(c.title, c.url, c.id) for c in chunks],
        )
    return {"chunks": len(chunks), "embedded": len(todo), "deleted": len(stale),
            "sources": len({c.source_id for c in chunks})}


def main(argv: list[str]) -> int:
    if "--dry" in argv:
        for c in build_chunks():
            print(f"{c.id:40s} {len(c.text.split()):4d} words  {c.title[:60]}")
        return 0
    try:
        stats = ingest(verbose=True)
    except OllamaError as e:
        print(f"Ollama is not reachable on localhost (start it, then re-run): {e}")
        return 1
    print(f"Indexed {stats['sources']} sources, {stats['chunks']} chunks "
          f"({stats['embedded']} embedded, {stats['deleted']} removed).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
