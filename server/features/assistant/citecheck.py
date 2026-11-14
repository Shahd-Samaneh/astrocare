"""Weak-citation check: does the cited reference passage actually support the sentence?

For each sentence that cites a reference passage, the sentence is embedded (nomic-embed-text,
query side) and compared with the cited passage's chunk vectors (cosine, best chunk). Below
`assistant_citation_min_similarity` the citation is dropped. If the sentence then has no
citation and is not about the user's data, "(general information)" is appended.
Citations to the user's own data and alerts are never touched. If embedding fails, the text
is returned unchanged (the check is a filter, never a reason to fail an answer).
"""
from __future__ import annotations

import re
from typing import Callable

import numpy as np

from .facts import SENTENCE
from .wording import CITE, is_about_user

GENERAL_EN = "(general information)"
GENERAL_AR = "(معلومة عامة)"

EmbedFn = Callable[[list[str]], list[list[float]]]


def _cos_max(v: list[float], vectors: list[list[float]]) -> float:
    q = np.asarray(v, dtype=np.float32)
    m = np.asarray([x for x in vectors if len(x) == len(v)], dtype=np.float32)
    if m.size == 0:
        return 1.0  # can't compare: keep the citation
    sims = (m @ q) / (np.linalg.norm(m, axis=1) * (np.linalg.norm(q) or 1.0) + 1e-9)
    return float(sims.max())


def check_citations(text: str, sources: list, embed_fn: EmbedFn, threshold: float, *, arabic: bool,
                    query_prefix: str = "search_query: ") -> tuple[str, list[dict]]:
    """Return (new text, report rows). `sources[i]` is cited as [i+1] in `text`."""
    ref_nums = {i + 1 for i, s in enumerate(sources) if s.is_reference and s.vectors}
    user_nums = {i + 1 for i, s in enumerate(sources) if not s.is_reference}
    sentences = [(m.start(), m.end(), m.group(0)) for m in SENTENCE.finditer(text)]
    todo = []
    for start, end, sent in sentences:
        nums = {int(n) for c in CITE.finditer(sent) for n in c.group(1).split(",")}
        if nums & ref_nums:
            todo.append((start, end, sent, nums))
    if not todo:
        return text, []
    try:
        vecs = embed_fn([query_prefix + CITE.sub("", s).strip() for _, _, s, _ in todo])
    except Exception:  # noqa: BLE001  never fail an answer because of the check
        return text, []

    report: list[dict] = []
    out, pos = [], 0
    for (start, end, sent, nums), v in zip(todo, vecs):
        drop = set()
        for n in sorted(nums & ref_nums):
            score = _cos_max(v, sources[n - 1].vectors)
            report.append({"sentence": sent.strip(), "source": sources[n - 1].id, "score": round(score, 3),
                           "kept": score >= threshold})
            if score < threshold:
                drop.add(n)
        new = sent
        if drop:
            def strip(m: re.Match[str]) -> str:
                keep = [n for n in m.group(1).split(",") if int(n) not in drop]
                return f"[{', '.join(k.strip() for k in keep)}]" if keep else "\x00"
            new = CITE.sub(strip, sent)
            # remove a dropped citation together with its joining word: "[8] and [6]" -> "[6]"
            new = re.sub(r"\x00\s*(?:and|or|&|,|و)\s*(?=\[)", "", new)
            new = re.sub(r"(?<=\])\s*(?:and|or|&|,|و)\s*\x00", "", new)
            new = re.sub(r"\s*(?:and|or|&|,|و)?\s*\x00", "", new)
            new = re.sub(r"[ \t]+([.,;:!?؟])", r"\1", new)
            if not CITE.search(new) and not is_about_user(new, set(), user_nums):
                tag = GENERAL_AR if arabic else GENERAL_EN
                m = re.search(r"([.!?؟]?)(\s*)$", new)
                new = f"{new[: m.start()].rstrip()} {tag}{m.group(1)}{m.group(2)}"
        out.append(text[pos:start])
        out.append(new)
        pos = end
    out.append(text[pos:])
    return "".join(out), report
