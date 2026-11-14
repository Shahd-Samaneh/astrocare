"""Template answer built from an alert, used when the local model is off, fails or is too slow.

- says why: "too slow" (no first token in time) or "not available" (off / error)
- explains the most important open alert (highest level, then newest), not just the newest
- the alert's missing data is listed once (on the "missing information" line, not also in the text)
- [1] is cited once, and each source appears once in the source list
"""
from __future__ import annotations

from typing import Literal

from . import store
from .arabic import ar_n
from .models import AssistantSource

FallbackReason = Literal["slow", "unavailable"]

_LABELS = {
    "en": {
        "intro_slow": "The local model is taking too long right now, so this is the template explanation of your most important open alert.",
        "intro_unavailable": "The local model is not available right now, so this is the template explanation of your most important open alert.",
        "alert": "Alert", "changed": "What changed", "data": "Data used",
        "factors": "Possible factors (a possible link, not a confirmed cause)", "next": "Next steps",
        "locked": "needs CMO review", "none": "none",
        "no_alert_slow": "The local model is taking too long right now, and there is no open alert to explain. Try again in a moment.",
        "no_alert_unavailable": "The local model is not available right now, and there is no open alert to explain. Try again in a moment.",
        "missing_slow": "The local model was too slow: this is a template answer, not an answer to your exact question",
        "missing_unavailable": "Local model unavailable: this is a template answer, not an answer to your exact question",
        "see_missing": "see the missing information below",
    },
    "ar": {
        "intro_slow": "الموديل المحلي بطيء كتير هلق، فهاد شرح جاهز (قالب) لأهم تنبيه مفتوح عندك.",
        "intro_unavailable": "الموديل المحلي مش متاح هلق، فهاد شرح جاهز (قالب) لأهم تنبيه مفتوح عندك.",
        "alert": "التنبيه", "changed": "شو تغيّر", "data": "البيانات المستخدمة",
        "factors": "عوامل محتملة (ارتباط محتمل، مش سبب مؤكد)", "next": "الخطوات الجاية",
        "locked": "بحاجة لمراجعة الـ CMO", "none": "ما في",
        "no_alert_slow": "الموديل المحلي بطيء كتير هلق، وما في تنبيه مفتوح لشرحه. جرّب كمان شوي.",
        "no_alert_unavailable": "الموديل المحلي مش متاح هلق، وما في تنبيه مفتوح لشرحه. جرّب كمان شوي.",
        "missing_slow": "الموديل المحلي كان بطيء كتير: هاد جواب من قالب، مش جواب لسؤالك بالضبط",
        "missing_unavailable": "الموديل المحلي مش متاح: هاد جواب من قالب، مش جواب لسؤالك بالضبط",
        "see_missing": "شوف المعلومات الناقصة تحت",
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


def build_fallback(alert: dict | None, *, arabic: bool,
                   reason: FallbackReason = "unavailable") -> tuple[str, list[AssistantSource], list[str]]:
    """Return (answer, sources, missing) from the alert's fields."""
    L = _LABELS["ar" if arabic else "en"]
    if not alert:
        return L[f"no_alert_{reason}"], [], [L[f"missing_{reason}"]]

    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items) if items else f"- {L['none']}"

    steps = []
    for s in alert.get("nextSteps") or []:
        # a locked step may name a medicine: never show it from the assistant
        steps.append(f"({L['locked']})" if s.get("lockedForCMO") else s.get("text", ""))
    steps = dedupe(steps)
    n_used = len(alert.get("dataUsed") or [])
    used = ar_n(n_used, "reading") if arabic else f"{n_used} reading{'' if n_used == 1 else 's'}"
    missing = dedupe(alert.get("missing") or [])
    if missing:
        used += f" ({L['see_missing']})"

    answer = "\n\n".join([
        L[f"intro_{reason}"],
        f"**{L['alert']} {alert.get('ruleId')}: {alert.get('title')}**",
        f"**{L['changed']}:** {alert.get('whatChanged')} [1]",
        f"**{L['data']}:** {used}",
        f"**{L['factors']}:**\n{bullets(dedupe(alert.get('possibleFactors') or []))}",
        f"**{L['next']}:**\n{bullets(steps)}",
    ])

    sources = [AssistantSource(id=f"alert:{alert.get('id')}", title=f"{L['alert']} {alert.get('ruleId')}: {alert.get('title')}")]
    refs = store.source_meta()
    for i, src in enumerate(alert.get("sources") or []):
        src = str(src)
        if src in refs:  # a reference id (same ids as references/<id>.txt)
            title, url = refs[src]
            sources.append(AssistantSource(id=src, title=title, url=url))
        else:
            sources.append(AssistantSource(id=f"alert-source:{i}", title=src))
    return answer, dedupe_sources(sources), dedupe([L[f"missing_{reason}"], *missing])


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
