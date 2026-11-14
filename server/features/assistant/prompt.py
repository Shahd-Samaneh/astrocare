"""Prompt building and answer post-processing for the local model.

Prompt layout (for Ollama's prompt cache: the longest identical prefix is reused between calls):
  system  = SYSTEM_PROMPT, byte-for-byte the same on every call (no language, no data)
  user    = 1. your data (vitals, sleep, attention, exercise, check-ins) + alerts   (changes slowly)
            2. reference passages                                                  (per question)
            3. LANGUAGE line + QUESTION                                            (per question, last)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .citecheck import EmbedFn, check_citations
from .facts import SENTENCE, Fact, build_facts, contradicted_facts
from .retrieval import Hit
from .wording import address_user, soften_causes


@dataclass
class PromptSource:
    id: str
    title: str
    url: str | None
    body: str
    vectors: list[list[float]] = field(default_factory=list)  # reference passages only (citation check)

    @property
    def is_reference(self) -> bool:
        return not (self.id.startswith("user-data:") or self.id.startswith("alert:"))


@dataclass
class Prompt:
    system: str
    user: str
    sources: list[PromptSource] = field(default_factory=list)  # index i is cited as [i+1]
    facts: dict[str, Fact] = field(default_factory=dict)      # fixed facts shown in the data blocks


SYSTEM_PROMPT = """You are the AstroCare onboard health assistant for an astronaut on a deep-space mission with no link to Earth.
Rules (all mandatory):
1. Use ONLY the numbered sources in the user message. Do not use outside knowledge.
2. Cite every piece of information with its source number in square brackets, e.g. [2]. Only cite numbers that exist.
3. If the sources do not contain the answer, say clearly that this information is not in the available data or references. Never guess.
4. Never suggest a medication, a medicine name, a dose or a diagnosis. If the question needs one, say it needs the crew medical officer (CMO).
5. Talk about possible factors, never causes. Use the words "possible link, not a confirmed cause" when you connect data to a factor.
6. If data is marked stale or missing, say that it is stale or missing.
7. When the question is about the user's own data, cover every "Your data" source (vital signs, sleep, attention tests, exercise, check-ins) and cite each one; say so when a source has no data or is not shared.
8. A line starting with "FIXED FACT:" holds exact values computed from the data. Use those numbers and words exactly as written, cite that source, and never contradict them (for example, do not say "no lapses" if the fact gives lapses, and do not call data stale unless the fact says stale).
9. All data is simulated. Keep the answer short: at most 6 sentences.
10. Talk to the user directly as "you" and "your". Never write "the astronaut" or "the user".
11. Write the answer in the language given on the LANGUAGE line.
12. Finish with one last line, exactly in this form (the word MISSING stays in English):
MISSING: <information you needed but did not find, separated by ";">
or
MISSING: none"""

# Arabic answers drift into general medical claims more often: one extra rule, in the user message
# tail (so SYSTEM_PROMPT stays byte-identical and cached).
ARABIC_RULE = "RULE: Do not add medical claims that aren't in the context above."

# kept for callers that format it; the prompt no longer has placeholders
SYSTEM_TEMPLATE = SYSTEM_PROMPT

NOT_SHARED = "Not shared with the assistant (permission off)."
NO_DATA = "No data recorded in the last 7 days."

# (source id, title, context key, notShared label)
DATA_SOURCES = [
    ("user-data:vitals", "Your data: vital signs (latest)", "vitals", "vitals"),
    ("user-data:sleep", "Your data: sleep (7 days)", "sleep7d", "sleep"),
    ("user-data:attention", "Your data: attention tests (7 days)", "attention7d", "attention tests"),
    ("user-data:exercise", "Your data: exercise today", "exerciseToday", "exercise"),
    ("user-data:checkins", "Your data: check-ins (7 days)", "checkins7d", "check-ins (permission off)"),
]


def _compact(v: object) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


_FACT_FOR_SOURCE = {"user-data:sleep": "sleep", "user-data:attention": "attention",
                    "user-data:vitals": "vitals", "user-data:exercise": "exercise"}


def _data_body(ctx: dict, key: str, not_shared_label: str, fact: Fact | None) -> str:
    if not_shared_label in (ctx.get("notShared") or []):
        return NOT_SHARED
    v = ctx.get(key)
    if not v:
        return NO_DATA
    return (f"FIXED FACT: {fact.en}\nDATA: " if fact else "") + _compact(v)


def _data_and_alert_sources(ctx: dict, facts: dict[str, Fact]) -> list[PromptSource]:
    data_sources = [PromptSource(sid, title, None, _data_body(ctx, key, label, facts.get(_FACT_FOR_SOURCE.get(sid, ""))))
                    for sid, title, key, label in DATA_SOURCES]
    alert_sources = [
        PromptSource(f"alert:{a['id']}", f"Alert {a['ruleId']}: {a['title']}", None,
                     _compact({k: v for k, v in a.items() if k != "id"}))
        for a in ctx.get("alerts") or []
    ]
    return data_sources + alert_sources


def _block(n: int, s: PromptSource) -> str:
    return f"[{n}] {s.title}\n{s.body}"


def user_data_prefix(ctx: dict) -> str:
    """The data + alerts part that starts every user message (identical for every question
    while the data is unchanged). Startup priming sends exactly this, so it gets cached."""
    fixed = _data_and_alert_sources(ctx, build_facts(ctx))
    return ("YOUR DATA AND ALERTS (simulated):\n\n" + "\n\n".join(_block(i + 1, s) for i, s in enumerate(fixed))
            + "\n\nREFERENCE PASSAGES:\n\n")


def build_prompt(question: str, ctx: dict, hits: list[Hit], *, arabic: bool) -> Prompt:
    facts = build_facts(ctx)
    fixed = _data_and_alert_sources(ctx, facts)
    by_source: dict[str, PromptSource] = {}
    for h in hits:  # merge chunks of the same reference into one numbered source
        if h.source_id in by_source:
            by_source[h.source_id].body += "\n...\n" + h.text
        else:
            by_source[h.source_id] = PromptSource(h.source_id, h.title, h.url, h.text)
        if h.embedding:
            by_source[h.source_id].vectors.append(h.embedding)
    ref_sources = list(by_source.values())
    sources = fixed + ref_sources

    user = (
        user_data_prefix(ctx)
        + ("\n\n".join(_block(len(fixed) + i + 1, s) for i, s in enumerate(ref_sources)) if ref_sources else "(none found)")
        # per-question tail (after the cached prefix): the Arabic-only rule goes here, not in SYSTEM_PROMPT
        + ("\n\n" + ARABIC_RULE if arabic else "")
        + f"\n\nLANGUAGE: {'Arabic' if arabic else 'English'}\nQUESTION: {question}"
    )
    return Prompt(system=SYSTEM_PROMPT, user=user, sources=sources, facts=facts)


_MISSING_LINE = re.compile(r"^[ \t*_>-]*MISSING[*_]*\s*[:：][*_]*\s*(.*)$", re.I | re.M)
_NONE = {"none", "nothing", "n/a", "-", "لا شيء", "لا يوجد", "ما في", "لا"}
_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
CITE_ANY = _CITE  # "[1]", "[1, 2]" (and each part of "[1][2]")


@dataclass
class Parsed:
    answer: str
    sources: list[PromptSource]
    missing: list[str]
    citation_report: list[dict] = field(default_factory=list)  # weak-citation check scores


# Phrases that name one "Your data" area in a sentence (English + Arabic).
# Only wording that clearly points at the user's own data ("your ...", "... data"), so a
# general sentence from a reference passage is never attributed to the user's data.
_DATA_PHRASES = {
    "user-data:vitals": r"your (vital signs?|vitals|heart rate|spo₂|spo2|blood pressure|skin temperature|respiration rate)"
                        r"|vital signs? data|حيوياتك|علاماتك الحيوية|نبضك",
    "user-data:sleep": r"your sleep|sleep data|you (have |had )?slept|نومك|بيانات النوم",
    "user-data:attention": r"your (attention|reaction time|median reaction)|attention tests? (data|results)|اختبارات الانتباه تبعك|انتباهك",
    "user-data:exercise": r"your exercise|exercise data|تمرينك|بيانات التمرين",
    "user-data:checkins": r"your (check-?ins?|mood|stress)|check-?in data|مزاجك|توترك",
}


_LABEL_ONLY = re.compile(r"^[\s*_#>-]*([^\W\d_][\w\s,'()/&-]{0,40}?)\s*[:：]\s*[*_]*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _drop_label_only_lines(text: str) -> str:
    """Remove lines that are only a label the model invented ("Possible link:", "NOT A CONFIRMED
    CAUSE:") with nothing after them. A label followed by a list ("Next steps:" + bullets) stays."""
    lines = text.split("\n")
    out: list[str] = []
    for i, line in enumerate(lines):
        m = _LABEL_ONLY.match(line)
        if m and len(m.group(1).split()) <= 5 and not _CITE.search(line):
            nxt = next((ln for ln in lines[i + 1:] if ln.strip()), "")
            if not _LIST_ITEM.match(nxt):
                continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _alert_phrases(body: str) -> list[str]:
    """Distinctive phrases of an alert (its possible factors and what-changed text, 12+ chars)."""
    try:
        a = json.loads(body)
    except ValueError:
        return []
    items = list(a.get("possibleFactors") or []) + [a.get("whatChanged") or ""]
    return [p.strip().rstrip(".") for p in items if len(p.strip()) >= 12]


def _cite_title_headings(text: str, prompt: Prompt) -> str:
    """A small model often names a source instead of citing [n]:
    - a heading line that is a source's title ("Your data: sleep (7 days)")
    - a sentence quoting an alert's title ("...Skin temperature: no recent data...")
    - a sentence about one "Your data" area ("Your sleep data shows ...")
    Each such line or sentence without a citation gets that source's number."""
    lines = text.split("\n")
    for i, s in enumerate(prompt.sources):
        pat = re.compile(rf"^[\s*#>_-]*{re.escape(s.title)}[\s*_:]*$", re.I)
        for j, line in enumerate(lines):
            if pat.match(line) and not _CITE.search(line):
                lines[j] = f"{line.rstrip()} [{i + 1}]"
    text = "\n".join(lines)

    matchers: list[tuple[int, re.Pattern[str]]] = []
    for i, s in enumerate(prompt.sources):
        if s.id.startswith("alert:"):
            alert_title = s.title.split(": ", 1)[1] if ": " in s.title else s.title
            # the title, or the alert's own wording (a possible factor, what changed) quoted in the sentence
            phrases = [alert_title] + _alert_phrases(s.body)
            matchers.append((i + 1, re.compile("|".join(re.escape(p) for p in phrases), re.I)))
        elif s.id in _DATA_PHRASES and s.body not in (NOT_SHARED, NO_DATA):
            matchers.append((i + 1, re.compile(rf"\b({_DATA_PHRASES[s.id]})", re.I)))

    def cite_sentence(m: re.Match[str]) -> str:
        sent = m.group(0)
        if _CITE.search(sent) or not sent.strip():
            return sent
        nums = sorted({n for n, pat in matchers if pat.search(sent)})
        if not nums:
            return sent
        tag = f" [{', '.join(map(str, nums))}]"
        end = len(sent.rstrip())
        if end and sent[end - 1] in ".!?؟":
            return sent[: end - 1] + tag + sent[end - 1:]
        return sent[:end] + tag + sent[end:]

    return SENTENCE.sub(cite_sentence, text) if matchers else text


def _enforce_facts(text: str, prompt: Prompt, *, arabic: bool) -> str:
    """Replace each sentence about the user's data that contradicts a FIXED FACT with that
    fact line (cited with the fact's source number in this prompt). A fact is written once;
    later contradicting sentences are dropped."""
    if not prompt.facts:
        return text
    num = {s.id: i + 1 for i, s in enumerate(prompt.sources)}
    written: set[str] = set()

    def fix(m: re.Match[str]) -> str:
        sent = m.group(0)
        bad = contradicted_facts(_CITE.sub("", sent), prompt.facts)
        if not bad:
            return sent
        lead = re.match(r"^\s*(?:[-*•]\s+)?", sent).group(0)
        tail = sent[len(sent.rstrip()):]
        parts = []
        for f in bad:
            if f.key in written:
                continue
            written.add(f.key)
            line = f.text(arabic)
            cite = f" [{num[f.source_id]}]" if f.source_id in num else ""
            parts.append(line[:-1] + cite + "." if line.endswith(".") else line + cite)
        return (lead + " ".join(parts) + tail) if parts else tail

    return SENTENCE.sub(fix, text)


def parse_answer(text: str, prompt: Prompt, *, arabic: bool = False,
                 embed_fn: EmbedFn | None = None, min_similarity: float | None = None) -> Parsed:
    """Split off the MISSING line, cite named sources, replace sentences that contradict a
    fixed fact, soften cause wording about the user's data, drop reference citations the
    passage doesn't support (when embed_fn is given), keep only valid citations and
    renumber them 1..n in the order of the returned sources list."""
    missing: list[str] = []
    matches = list(_MISSING_LINE.finditer(text))
    if matches:
        m = matches[-1]
        items = [i.strip().strip(".") for i in re.split(r"[;؛]", m.group(1))]
        missing = [i for i in items if i and i.lower() not in _NONE]
        text = (text[: m.start()] + text[m.end():]).strip()

    text = _drop_label_only_lines(text)
    text = _cite_echoed_facts(text, prompt)
    text = _cite_title_headings(text, prompt)
    text = _enforce_facts(text, prompt, arabic=arabic)
    user_nums = {i + 1 for i, s in enumerate(prompt.sources) if not s.is_reference}
    text = soften_causes(text, user_nums, arabic=arabic)
    if not arabic:
        text = address_user(text)
    report: list[dict] = []
    if embed_fn is not None and min_similarity is not None:
        text, report = check_citations(text, prompt.sources, embed_fn, float(min_similarity), arabic=arabic)
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
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    text = split_citations(merge_list_citations(text))
    return Parsed(answer=text, sources=[prompt.sources[i] for i in order],
                  missing=_drop_false_missing(missing, prompt.facts), citation_report=report)


_TRAIL_CITES = re.compile(r"((?:[ \t]*\[\d+(?:\s*,\s*\d+)*\])+)([ \t]*[.!?؟]?)[ \t]*$")


def _trail_set(line: str) -> frozenset[int]:
    m = _TRAIL_CITES.search(line)
    return frozenset(int(n) for c in _CITE.finditer(m.group(1)) for n in c.group(1).split(",")) if m else frozenset()


def merge_list_citations(text: str) -> str:
    """Consecutive list items ending with the same citations: cite once, on the last item.
    '- A [1, 2]\\n- B [1, 2]' -> '- A\\n- B [1, 2]'."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        key = _trail_set(lines[i]) if _LIST_ITEM.match(lines[i]) else frozenset()
        j = i
        while key and j + 1 < len(lines) and _LIST_ITEM.match(lines[j + 1]) and _trail_set(lines[j + 1]) == key:
            j += 1
        for k in range(i, j):  # all but the last item of the run
            m = _TRAIL_CITES.search(lines[k])
            lines[k] = lines[k][: m.start()].rstrip() + m.group(2).strip()
        i = j + 1
    return "\n".join(lines)


def split_citations(text: str) -> str:
    """'[1, 2]' -> '[1][2]' (how the screen shows citations)."""
    return _CITE.sub(lambda m: "".join(f"[{n.strip()}]" for n in m.group(1).split(",")), text)


# ---- "my data" questions: answered in code from the fixed facts (direct.py), never by the model
_DATA_QUESTION = re.compile(
    r"\b(my (data|numbers|stats|readings)|(last|past) (7|seven) days|how am i doing|summar(y|ise|ize) (of )?my)\b"
    r"|بياناتي|[اآ]خر (7|سبع|سبعة) [اأ]يام|ملخص بيانات",
    re.I,
)


def is_data_question(question: str) -> bool:
    return bool(_DATA_QUESTION.search(question))


# a "missing" item that names a whole data area (not one reading)
_AREA_IN_MISSING = {
    "vitals": re.compile(r"vital signs?|vitals|العلامات الحيوية|الحيويات", re.I),
    "sleep": re.compile(r"\bsleep\b|النوم", re.I),
    "attention": re.compile(r"attention|الانتباه", re.I),
    "exercise": re.compile(r"exercise|التمرين", re.I),
}
_SPECIFIC_READING = re.compile(r"blood pressure|\bbp\b|ضغط", re.I)


def _drop_false_missing(missing: list[str], facts: dict) -> list[str]:
    """Drop a missing item that says a whole data area is missing when a fixed fact for that
    area exists. Items about a single reading (e.g. blood pressure today) are kept."""
    out = []
    for item in missing:
        area = next((k for k, pat in _AREA_IN_MISSING.items() if pat.search(item)), None)
        if area and area in facts and not _SPECIFIC_READING.search(item):
            continue
        out.append(item)
    return out


_FACT_LABEL = re.compile(r"\bFIXED FACTS?\s*:\s*", re.I)
_ECHOED_DATA = re.compile(r"^[ \t*_>-]*DATA:\s*[\[{].*$\n?", re.M)


def _cite_echoed_facts(text: str, prompt: Prompt) -> str:
    """The model sometimes copies a 'FIXED FACT: ...' line. Drop the label and cite the
    fact's source (the line is exact, so it only needs its citation)."""
    text = _FACT_LABEL.sub("", text)
    text = _ECHOED_DATA.sub("", text)  # a copied raw "DATA: {...}" line from the prompt
    num = {s.id: i + 1 for i, s in enumerate(prompt.sources)}
    for f in prompt.facts.values():
        body = f.en.rstrip(".")
        i = text.find(body)
        if i < 0 or f.source_id not in num:
            continue
        after = text[i + len(body):]
        if _CITE.match(after.lstrip(" .")[:8] or ""):
            continue
        text = text[: i + len(body)] + f" [{num[f.source_id]}]" + after
    return text
