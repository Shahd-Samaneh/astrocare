"""Prompt building and answer post-processing for the local model."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .retrieval import Hit


@dataclass
class PromptSource:
    id: str
    title: str
    url: str | None
    body: str


@dataclass
class Prompt:
    system: str
    user: str
    sources: list[PromptSource] = field(default_factory=list)  # index i is cited as [i+1]


SYSTEM_TEMPLATE = """You are the AstroCare onboard health assistant for an astronaut on a deep-space mission with no link to Earth.
Rules (all mandatory):
1. Use ONLY the numbered SOURCES in the user message. Do not use outside knowledge.
2. Cite every piece of information with its source number in square brackets, e.g. [2]. Only cite numbers that exist.
3. If the SOURCES do not contain the answer, say clearly that this information is not in the available data or references. Never guess.
4. Never suggest a medication, a medicine name, a dose or a diagnosis. If the question needs one, say it needs the crew medical officer (CMO).
5. Talk about possible factors, never causes. Use the words "possible link, not a confirmed cause" when you connect data to a factor.
6. If data is marked stale or missing, say that it is stale or missing.
7. All data is simulated. Keep the answer short: at most 6 sentences.
8. Write the answer in {language}.
9. Finish with one last line, exactly in this form (the word MISSING stays in English):
MISSING: <information you needed but did not find, separated by ";">
or
MISSING: none"""


def _user_data_body(ctx: dict) -> str:
    data = {k: v for k, v in ctx.items() if k not in {"alerts", "mockSources"}}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def build_prompt(question: str, ctx: dict, hits: list[Hit], *, arabic: bool) -> Prompt:
    sources: list[PromptSource] = [
        PromptSource("user-data", "Your AstroCare data (simulated, last 7 days)", None, _user_data_body(ctx)),
    ]
    for a in ctx.get("alerts") or []:
        body = json.dumps({k: v for k, v in a.items() if k != "id"}, ensure_ascii=False, separators=(",", ":"))
        sources.append(PromptSource(f"alert:{a['id']}", f"Alert {a['ruleId']}: {a['title']}", None, body))
    by_source: dict[str, PromptSource] = {}
    for h in hits:  # merge chunks of the same reference into one numbered source
        if h.source_id in by_source:
            by_source[h.source_id].body += "\n...\n" + h.text
        else:
            by_source[h.source_id] = PromptSource(h.source_id, h.title, h.url, h.text)
    sources.extend(by_source.values())

    blocks = [f"[{i + 1}] {s.title}\n{s.body}" for i, s in enumerate(sources)]
    user = "SOURCES:\n\n" + "\n\n".join(blocks) + f"\n\nQUESTION: {question}"
    system = SYSTEM_TEMPLATE.format(language="Arabic" if arabic else "English")
    return Prompt(system=system, user=user, sources=sources)


_MISSING_LINE = re.compile(r"^[ \t*_>-]*MISSING[*_]*\s*[:：][*_]*\s*(.*)$", re.I | re.M)
_NONE = {"none", "nothing", "n/a", "-", "لا شيء", "لا يوجد", "ما في", "لا"}
_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass
class Parsed:
    answer: str
    sources: list[PromptSource]
    missing: list[str]


def parse_answer(text: str, prompt: Prompt) -> Parsed:
    """Split off the MISSING line, keep only valid citations and renumber them 1..n
    in the order of the returned sources list."""
    missing: list[str] = []
    matches = list(_MISSING_LINE.finditer(text))
    if matches:
        m = matches[-1]
        items = [i.strip().strip(".") for i in re.split(r"[;؛]", m.group(1))]
        missing = [i for i in items if i and i.lower() not in _NONE]
        text = (text[: m.start()] + text[m.end():]).strip()

    order: list[int] = []  # 0-based prompt indexes, in first-cited order
    for m in _CITE.finditer(text):
        for n in m.group(1).split(","):
            idx = int(n) - 1
            if 0 <= idx < len(prompt.sources) and idx not in order:
                order.append(idx)
    new_num = {old: new + 1 for new, old in enumerate(order)}

    def _renumber(m: re.Match[str]) -> str:
        nums = [new_num.get(int(n) - 1) for n in m.group(1).split(",")]
        nums = [str(n) for n in nums if n]
        return f"[{', '.join(nums)}]" if nums else ""

    text = _CITE.sub(_renumber, text)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text).strip()
    return Parsed(answer=text, sources=[prompt.sources[i] for i in order], missing=missing)
