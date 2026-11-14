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


SYSTEM_PROMPT = """You are the AstroCare onboard health assistant for an astronaut on a deep-space mission with no link to Earth.
Rules (all mandatory):
1. Use ONLY the numbered sources in the user message. Do not use outside knowledge.
2. Cite every piece of information with its source number in square brackets, e.g. [2]. Only cite numbers that exist.
3. If the sources do not contain the answer, say clearly that this information is not in the available data or references. Never guess.
4. Never suggest a medication, a medicine name, a dose or a diagnosis. If the question needs one, say it needs the crew medical officer (CMO).
5. Talk about possible factors, never causes. Use the words "possible link, not a confirmed cause" when you connect data to a factor.
6. If data is marked stale or missing, say that it is stale or missing.
7. When the question is about the user's own data, cover every "Your data" source (vital signs, sleep, attention tests, exercise, check-ins) and cite each one; say so when a source has no data or is not shared.
8. All data is simulated. Keep the answer short: at most 6 sentences.
9. Write the answer in the language given on the LANGUAGE line.
10. Finish with one last line, exactly in this form (the word MISSING stays in English):
MISSING: <information you needed but did not find, separated by ";">
or
MISSING: none"""

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


def _data_body(ctx: dict, key: str, not_shared_label: str) -> str:
    if not_shared_label in (ctx.get("notShared") or []):
        return NOT_SHARED
    v = ctx.get(key)
    return _compact(v) if v else NO_DATA


def build_prompt(question: str, ctx: dict, hits: list[Hit], *, arabic: bool) -> Prompt:
    data_sources = [PromptSource(sid, title, None, _data_body(ctx, key, label))
                    for sid, title, key, label in DATA_SOURCES]
    alert_sources = [
        PromptSource(f"alert:{a['id']}", f"Alert {a['ruleId']}: {a['title']}", None,
                     _compact({k: v for k, v in a.items() if k != "id"}))
        for a in ctx.get("alerts") or []
    ]
    by_source: dict[str, PromptSource] = {}
    for h in hits:  # merge chunks of the same reference into one numbered source
        if h.source_id in by_source:
            by_source[h.source_id].body += "\n...\n" + h.text
        else:
            by_source[h.source_id] = PromptSource(h.source_id, h.title, h.url, h.text)
    ref_sources = list(by_source.values())

    sources = data_sources + alert_sources + ref_sources
    num = {id(s): i + 1 for i, s in enumerate(sources)}

    def block(s: PromptSource) -> str:
        return f"[{num[id(s)]}] {s.title}\n{s.body}"

    user = (
        "YOUR DATA AND ALERTS (simulated):\n\n" + "\n\n".join(block(s) for s in data_sources + alert_sources)
        + "\n\nREFERENCE PASSAGES:\n\n"
        + ("\n\n".join(block(s) for s in ref_sources) if ref_sources else "(none found)")
        + f"\n\nLANGUAGE: {'Arabic' if arabic else 'English'}\nQUESTION: {question}"
    )
    return Prompt(system=SYSTEM_PROMPT, user=user, sources=sources)


_MISSING_LINE = re.compile(r"^[ \t*_>-]*MISSING[*_]*\s*[:：][*_]*\s*(.*)$", re.I | re.M)
_NONE = {"none", "nothing", "n/a", "-", "لا شيء", "لا يوجد", "ما في", "لا"}
_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass
class Parsed:
    answer: str
    sources: list[PromptSource]
    missing: list[str]


# Phrases that name one "Your data" area in a sentence (English + Arabic).
# Only wording that clearly points at the user's own data ("your ...", "... data"), so a
# general sentence from a reference passage is never attributed to the user's data.
_DATA_PHRASES = {
    "user-data:vitals": r"your (vital signs?|vitals|heart rate|spo₂|spo2|blood pressure|skin temperature|respiration rate)"
                        r"|vital signs? data|حيوياتك|علاماتك الحيوية|نبضك",
    "user-data:sleep": r"your sleep|sleep data|you slept|نومك|بيانات النوم",
    "user-data:attention": r"your (attention|reaction time|median reaction)|attention tests? (data|results)|اختبارات الانتباه تبعك|انتباهك",
    "user-data:exercise": r"your exercise|exercise data|تمرينك|بيانات التمرين",
    "user-data:checkins": r"your (check-?ins?|mood|stress)|check-?in data|مزاجك|توترك",
}
_SENTENCE = re.compile(r"[^.!?؟\n]+[.!?؟]?")


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
            matchers.append((i + 1, re.compile(re.escape(alert_title), re.I)))
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

    return _SENTENCE.sub(cite_sentence, text) if matchers else text


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

    text = _cite_title_headings(text, prompt)
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


# ---- "my data" questions: always cover sleep and attention --------------------------------
_DATA_QUESTION = re.compile(
    r"\b(my (data|numbers|week|stats|health)|last (7|seven) days|this week|past week|how am i doing|summar\w*)\b"
    r"|بياناتي|اخر 7 ايام|آخر 7 أيام|اخر سبع ايام|آخر سبع أيام|هالاسبوع|هذا الاسبوع|ملخص",
    re.I,
)
_LABELS = {
    "en": {"sleep": "Sleep, last 7 days", "nights": "nights", "avg": "average", "short": "shortest",
           "last": "last night", "awk": "awakenings per night", "att": "Attention tests, last 7 days",
           "tests": "tests", "median": "median reaction time", "from": "from", "to": "to", "lapses": "lapses in the latest test"},
    "ar": {"sleep": "النوم، آخر 7 أيام", "nights": "ليالي", "avg": "المعدل", "short": "أقصر ليلة",
           "last": "الليلة الماضية", "awk": "مرات الاستيقاظ بالليلة", "att": "اختبارات الانتباه، آخر 7 أيام",
           "tests": "اختبارات", "median": "متوسط زمن الاستجابة", "from": "من", "to": "إلى", "lapses": "الهفوات بآخر اختبار"},
}


def is_data_question(question: str) -> bool:
    return bool(_DATA_QUESTION.search(question))


def _sleep_line(s: dict, L: dict) -> str:
    return (f"{L['sleep']}: {s['nights']} {L['nights']}, {L['avg']} {s['average']}, {L['short']} {s['shortest']}, "
            f"{L['last']} {s['lastNight']}, {s['avgAwakenings']} {L['awk']}")


def _attention_line(tests: list[dict], L: dict) -> str:
    first, last = tests[0], tests[-1]
    return (f"{L['att']}: {len(tests)} {L['tests']}, {L['median']} {L['from']} {first['medianMs']:.0f} ms "
            f"{L['to']} {last['medianMs']:.0f} ms, {L['lapses']}: {last['lapses']}")


def ensure_data_coverage(parsed: Parsed, prompt: Prompt, ctx: dict, question: str, *, arabic: bool) -> Parsed:
    """For a "my data" question, add a cited factual line for sleep and for attention when the
    model left them out. Lines are built from the data only (no interpretation)."""
    if not is_data_question(question):
        return parsed
    L = _LABELS["ar" if arabic else "en"]
    cited = {s.id for s in parsed.sources}
    by_id = {s.id: s for s in prompt.sources}
    extra: list[tuple[str, PromptSource]] = []
    sleep, tests = ctx.get("sleep7d"), ctx.get("attention7d")
    if "user-data:sleep" not in cited and sleep and "sleep" not in (ctx.get("notShared") or []):
        extra.append((_sleep_line(sleep, L), by_id["user-data:sleep"]))
    if "user-data:attention" not in cited and tests and "attention tests" not in (ctx.get("notShared") or []):
        extra.append((_attention_line(tests, L), by_id["user-data:attention"]))
    if not extra:
        return parsed
    sources = list(parsed.sources)
    lines = []
    for text, src in extra:
        sources.append(src)
        lines.append(f"- {text} [{len(sources)}]")
    return Parsed(answer=parsed.answer.rstrip() + "\n\n" + "\n".join(lines), sources=sources, missing=parsed.missing)
