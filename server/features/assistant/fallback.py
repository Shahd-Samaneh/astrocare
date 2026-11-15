"""Template answer built from an alert, used when the local model is off, fails or is too slow.

- says why ("too slow" / "not available") in a note shown under the badge, not in the answer
  or the missing list
- explains the most important open alert (highest level, then newest), not just the newest
- the alert's missing data is listed once (on the "missing information" line, not also in the text)
- [1] is cited once per list (at its end), and each source appears once in the source list
- build_alert_answer is also the no-model answer to "why did I get the alert?"
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from server.core.config import REFERENCES_DIR

from .arabic import ar_n, en_n
from .models import AnswerStep, AssistantSource

FallbackReason = Literal["slow", "unavailable"]

_LABELS = {
    "en": {
        "intro_slow": "The local model is taking too long right now, so this is the template explanation of your most important open alert.",
        "intro_unavailable": "The local model is not available right now, so this is the template explanation of your most important open alert.",
        "alert": "Alert", "changed": "What changed", "data": "Data used",
        "factors": "Possible factors (a possible link, not a confirmed cause)", "next": "Next steps",
        "locked": "needs CMO review", "none": "none",
        "no_alert": "There is no open alert to explain right now. Try again in a moment.",
        "see_missing": "see the missing information below", "background": "Background",
    },
    "ar": {
        "intro_slow": "الموديل المحلي بطيء كتير هلق، فهاد شرح جاهز (قالب) لأهم تنبيه مفتوح عندك.",
        "intro_unavailable": "الموديل المحلي مش متاح هلق، فهاد شرح جاهز (قالب) لأهم تنبيه مفتوح عندك.",
        "alert": "التنبيه", "changed": "شو تغيّر", "data": "البيانات المستخدمة",
        "factors": "عوامل محتملة (ارتباط محتمل، مش سبب مؤكد)", "next": "الخطوات الجاية",
        "locked": "بحاجة لمراجعة الـ CMO", "none": "ما في",
        "no_alert": "ما في تنبيه مفتوح لشرحه هلق. جرّب كمان شوي.",
        "see_missing": "شوف المعلومات الناقصة تحت", "background": "خلفية",
    },
}

_LEVEL_RANK = {"urgent": 3, "review": 2, "info": 1}


def pick_alert(alerts: list[dict]) -> dict | None:
    """The alert the template explains: open alerts first, then the highest level, then the newest."""
    if not alerts:
        return None
    open_ = [a for a in alerts if a.get("status") != "closed"] or alerts
    return max(open_, key=lambda a: (_LEVEL_RANK.get(a.get("level"), 0), a.get("ts") or ""))


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for i in items:
        key = " ".join(str(i).split()).casefold().rstrip(".")
        if key and key not in seen:
            seen.add(key)
            out.append(i)
    return out


def fallback_note(reason: FallbackReason, *, arabic: bool) -> str:
    """The small notice shown under the badge: why this is a template answer."""
    return _LABELS["ar" if arabic else "en"][f"intro_{reason}"]


def build_alert_answer(alert: dict, *, arabic: bool) -> tuple[str, list[AssistantSource], list[str]]:
    """Explain one alert from its own fields: (answer, sources, missing). Used for alert questions
    (no model) and by the template fallback. The alert is cited once, at the end of each list."""
    L = _LABELS["ar" if arabic else "en"]

    def bullets(items: list[str]) -> str:
        if not items:
            return f"- {L['none']}"
        return "\n".join(f"- {i}" for i in items[:-1] + [f"{items[-1]} [1]"])

    steps = []
    for s in alert.get("nextSteps") or []:
        # a locked step may name a medicine: never show it from the assistant
        steps.append(f"({L['locked']})" if s.get("lockedForCMO") else s.get("text", ""))
    steps = dedupe(steps)
    n_used = len(alert.get("dataUsed") or [])
    used = ar_n(n_used, "reading") if arabic else en_n(n_used, "reading")
    missing = dedupe(alert.get("missing") or [])
    if missing:
        used += f" ({L['see_missing']})"

    sources = [AssistantSource(id=f"alert:{alert.get('id')}", title=f"{L['alert']} {alert.get('ruleId')}: {alert.get('title')}")]
    # the alert's sources[] that are references/<id>.txt files (unknown ids are ignored)
    refs = reference_meta()
    for src in dict.fromkeys(str(s) for s in alert.get("sources") or []):
        if src in refs:
            title, url = refs[src]
            sources.append(AssistantSource(id=src, title=title, url=url))
    sources = dedupe_sources(sources)

    parts = [
        f"**{L['alert']} {alert.get('ruleId')}: {alert.get('title')}**",
        f"**{L['changed']}:** {str(alert.get('whatChanged') or '').rstrip('. ')} [1].",
        f"**{L['data']}:** {used}",
        f"**{L['factors']}:**\n{bullets(dedupe(alert.get('possibleFactors') or []))}",
        f"**{L['next']}:**\n{bullets(steps)}",
    ]
    if len(sources) > 1:  # "Background: [2][3]"
        parts.append(f"{L['background']}: " + "".join(f"[{n}]" for n in range(2, len(sources) + 1)))
    answer, cited = cited_only("\n\n".join(parts), sources)
    return answer, cited, missing


def reference_meta(ref_dir: Path | None = None) -> dict[str, tuple[str, str | None]]:
    """id -> (title, url) of every references/*.txt file, from its header (no index needed)."""
    from .ingest import parse_reference  # local import: ingest is a dev-time module

    out: dict[str, tuple[str, str | None]] = {}
    for path in sorted((ref_dir or REFERENCES_DIR).glob("*.txt")):
        try:
            doc = parse_reference(path)
        except (OSError, UnicodeDecodeError):
            continue
        out[doc.source_id] = (doc.title, doc.url)
    return out


ALERT_ID_TOKEN = "{alertId}"  # in NextStep.action.route: this alert's id


def step_link(step: dict) -> str | None:
    """In-app link for a next step, shown as a button: NextStep.action.route (Daily proposal §2,
    chosen over A13's `link`)."""
    action = step.get("action")
    return action.get("route") if isinstance(action, dict) else None


def answer_steps(alert: dict | None, *, arabic: bool) -> list[AnswerStep]:
    """The alert's next steps, in the same order and wording as the answer text. A CMO-locked
    step never shows its text and never gets a link."""
    if not alert:
        return []
    L = _LABELS["ar" if arabic else "en"]
    out: list[AnswerStep] = []
    seen: set[str] = set()
    for s in alert.get("nextSteps") or []:
        locked = bool(s.get("lockedForCMO"))
        text = f"({L['locked']})" if locked else str(s.get("text", ""))
        key = " ".join(text.split()).casefold().rstrip(".")
        if not key or key in seen:
            continue
        seen.add(key)
        link = None if locked else _in_app(step_link(s))
        if link and alert.get("id"):
            link = link.replace(ALERT_ID_TOKEN, str(alert["id"]))
        out.append(AnswerStep(text=text, link=link, locked_for_cmo=locked))
    return out


def _in_app(link: str | None) -> str | None:
    """Only same-app paths ("/daily#checkin", "/attention?retest=al-1"), never a host or scheme."""
    return link if link and link.startswith("/") and not link.startswith("//") else None


def build_fallback(alert: dict | None, *, arabic: bool,
                   reason: FallbackReason = "unavailable") -> tuple[str, list[AssistantSource], list[str]]:
    """Return (answer, sources, missing) from the alert's fields. `missing` holds only real
    missing data; the "template / too slow" notice is fallback_note(), shown under the badge."""
    L = _LABELS["ar" if arabic else "en"]
    if not alert:
        return L["no_alert"], [], []
    return build_alert_answer(alert, arabic=arabic)


_CITE_GROUP = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def cited_only(answer: str, sources: list[AssistantSource]) -> tuple[str, list[AssistantSource]]:
    """Keep only the sources the answer text cites, renumbered 1..n in first-cited order.
    A citation to a number with no source is removed. Used for every answer built in code."""
    order: list[int] = []
    for m in _CITE_GROUP.finditer(answer):
        for part in m.group(1).split(","):
            idx = int(part) - 1
            if 0 <= idx < len(sources) and idx not in order:
                order.append(idx)
    new_num = {old: new + 1 for new, old in enumerate(order)}

    def renumber(m: re.Match[str]) -> str:
        nums = [new_num[int(p) - 1] for p in m.group(1).split(",") if int(p) - 1 in new_num]
        return f"[{', '.join(str(n) for n in dict.fromkeys(nums))}]" if nums else "\x00"

    text = re.sub(r"[ \t]*\x00", "", _CITE_GROUP.sub(renumber, answer))  # "word [9]." -> "word."
    return text, [sources[i] for i in order]


def dedupe_sources(sources: list[AssistantSource]) -> list[AssistantSource]:
    """Each source once (same id, or same title)."""
    seen: set[str] = set()
    out = []
    for s in sources:
        keys = {s.id, " ".join(s.title.split()).casefold()}
        if keys & seen:
            continue
        seen |= keys
        out.append(s)
    return out
