"""Template answer built from an alert, used when the local model is off, fails or is too slow.

- says why ("too slow" / "not available") in a note shown under the badge, not in the answer
  or the missing list
- explains the most important open alert (highest level, then newest), not just the newest
- the alert's missing data is listed once (on the "missing information" line, not also in the text)
- [1] is cited once per list (at its end), and each source appears once in the source list
- build_alert_answer is also the no-model answer to "why did I get the alert?"
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
        "no_alert": "There is no open alert to explain right now. Try again in a moment.",
        "see_missing": "see the missing information below",
    },
    "ar": {
        "intro_slow": "الموديل المحلي بطيء كتير هلق، فهاد شرح جاهز (قالب) لأهم تنبيه مفتوح عندك.",
        "intro_unavailable": "الموديل المحلي مش متاح هلق، فهاد شرح جاهز (قالب) لأهم تنبيه مفتوح عندك.",
        "alert": "التنبيه", "changed": "شو تغيّر", "data": "البيانات المستخدمة",
        "factors": "عوامل محتملة (ارتباط محتمل، مش سبب مؤكد)", "next": "الخطوات الجاية",
        "locked": "بحاجة لمراجعة الـ CMO", "none": "ما في",
        "no_alert": "ما في تنبيه مفتوح لشرحه هلق. جرّب كمان شوي.",
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
    used = ar_n(n_used, "reading") if arabic else f"{n_used} reading{'' if n_used == 1 else 's'}"
    missing = dedupe(alert.get("missing") or [])
    if missing:
        used += f" ({L['see_missing']})"

    answer = "\n\n".join([
        f"**{L['alert']} {alert.get('ruleId')}: {alert.get('title')}**",
        f"**{L['changed']}:** {str(alert.get('whatChanged') or '').rstrip('. ')} [1].",
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
    return answer, dedupe_sources(sources), missing


def build_fallback(alert: dict | None, *, arabic: bool,
                   reason: FallbackReason = "unavailable") -> tuple[str, list[AssistantSource], list[str]]:
    """Return (answer, sources, missing) from the alert's fields. `missing` holds only real
    missing data; the "template / too slow" notice is fallback_note(), shown under the badge."""
    L = _LABELS["ar" if arabic else "en"]
    if not alert:
        return L["no_alert"], [], []
    return build_alert_answer(alert, arabic=arabic)


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
