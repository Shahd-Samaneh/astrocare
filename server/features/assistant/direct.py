"""Answers built in code, without the model (instant, exact, in the question's language).

1. Alert questions ("why did I get the alert?", "ليش طلعلي التنبيه؟", or a rule id like R-FAT-01)
   -> the alert's own fields: what changed, data used, possible factors, next steps.
   A rule id in the question picks that alert; otherwise the highest-level open alert.
2. "My data" questions ("last 7 days", "my data", "آخر 7 أيام", "بياناتي")
   -> one line per data area from the fixed facts (sleep, attention, vitals, exercise, check-ins),
   each cited; an area the user did not share says so, and is not sent anywhere.

Every other question goes to the local model.
"""
from __future__ import annotations

import re

from .arabic import ar_n, en_n
from .context import load_raw
from .facts import METRIC_NAMES, build_facts
from .fallback import _LEVEL_RANK, answer_steps, build_alert_answer, cited_only
from .models import AnswerStep, AssistantSource
from .prompt import DATA_SOURCES, is_data_question

__all__ = ["is_alert_question", "is_data_question", "alert_answer", "data_answer", "pick_alert_for"]

_RULE_ID = re.compile(r"\bR-[A-Z]{2,6}-\d{1,3}\b", re.I)
_ALERT_QUESTION = re.compile(
    r"\b(?:the|this|that|my|latest|last|current|open)\s+(?:alert|warning)s?\b"
    r"|\bwhy\b.*\balerts?\b|\balert(?:ed)?\s+me\b"
    r"|التنبيه|تنبيه|الإنذار|الانذار|إنذار|انذار",
    re.I,
)


def is_alert_question(question: str) -> bool:
    return bool(_RULE_ID.search(question) or _ALERT_QUESTION.search(question))


def pick_alert_for(question: str, alerts: list[dict]) -> dict | None:
    """The rule named in the question (open first), else the highest-level open alert, newest
    first among equals. Closed alerts are only used when the question names their rule."""
    def best(items: list[dict]) -> dict | None:
        return max(items, key=lambda a: (_LEVEL_RANK.get(a.get("level"), 0), a.get("ts") or "")) if items else None

    open_ = [a for a in alerts if a.get("status") != "closed"]
    m = _RULE_ID.search(question)
    if m:
        rid = m.group(0).upper()
        named = [a for a in alerts if str(a.get("ruleId", "")).upper() == rid]
        hit = best([a for a in named if a.get("status") != "closed"]) or best(named)
        if hit:
            return hit
    return best(open_)


_NO_ALERT = {
    "en": "You have no open alert right now.",
    "ar": "ما عندك أي تنبيه مفتوح هلق.",
}


def alert_answer(question: str, *, arabic: bool
                 ) -> tuple[str, list[AssistantSource], list[str], str | None, list[AnswerStep]]:
    """(answer, sources, missing, ruleId, nextSteps). Raw alerts: a CMO-locked step is never shown."""
    raw, _ = load_raw({"alerts"})
    alert = pick_alert_for(question, raw.get("alerts") or [])
    if not alert:
        return _NO_ALERT["ar" if arabic else "en"], [], [], None, []
    answer, sources, missing = build_alert_answer(alert, arabic=arabic)
    return answer, sources, missing, alert.get("ruleId"), answer_steps(alert, arabic=arabic)


# ---- "my data" summary --------------------------------------------------------------------
_T = {
    "en": {
        "head": "Your data from the last 7 days (simulated):",
        "not_shared": "{area}: not shared with the assistant (permission off).",
        "no_data": "{area}: no data recorded in the last 7 days.",
        "missing_area": "{area}: no data in the last 7 days",
        "missing_vital": "{name}: no reading today",
        "checkins": "Check-ins, last 7 days: {n}, {skipped} skipped; latest mood {mood}/5, stress {stress}/5.",
        "checkins_all_skipped": "Check-ins, last 7 days: {n}, all skipped.",
        "areas": {"vitals": "Vital signs", "sleep": "Sleep", "attention": "Attention tests",
                  "exercise": "Exercise", "checkins": "Check-ins"},
    },
    "ar": {
        "head": "بياناتك آخر 7 أيام (بيانات محاكاة):",
        "not_shared": "{area}: مش مشاركة مع المساعد (الإذن مسكّر).",
        "no_data": "{area}: ما في بيانات مسجّلة آخر 7 أيام.",
        "missing_area": "{area}: ما في بيانات آخر 7 أيام",
        "missing_vital": "{name}: ما في قراءة اليوم",
        "checkins": "تسجيلات الحالة، آخر 7 أيام: {n}، منها {skipped} متخطّاة؛ آخر مزاج {mood}/5، توتر {stress}/5.",
        "checkins_all_skipped": "تسجيلات الحالة، آخر 7 أيام: {n}، كلها متخطّاة.",
        "areas": {"vitals": "العلامات الحيوية", "sleep": "النوم", "attention": "اختبارات الانتباه",
                  "exercise": "التمرين", "checkins": "تسجيلات الحالة"},
    },
}

# source id -> (area key, context key, notShared label)
_AREA = {sid: (sid.split(":", 1)[1], key, label) for sid, _title, key, label in DATA_SOURCES}


def _checkins_line(items: list[dict], T: dict, arabic: bool) -> str:
    done = [c for c in items if not c.get("skipped")]
    n = ar_n(len(items), "checkin") if arabic else en_n(len(items), "check-in")
    if not done:
        return T["checkins_all_skipped"].format(n=n)
    last = done[-1]
    return T["checkins"].format(n=n, skipped=len(items) - len(done),
                                mood=last.get("mood", "?"), stress=last.get("stress", "?"))


def data_answer(ctx: dict, *, arabic: bool) -> tuple[str, list[AssistantSource], list[str]]:
    """(answer, sources, missing) from the fixed facts. Each data line cites its own source."""
    T = _T["ar" if arabic else "en"]
    facts = {f.source_id: f for f in build_facts(ctx).values()}
    not_shared = ctx.get("notShared") or []
    lines: list[str] = []
    sources: list[AssistantSource] = []
    missing: list[str] = []

    for sid, title, key, label in DATA_SOURCES:
        area = T["areas"][_AREA[sid][0]]
        if label in not_shared:
            lines.append(f"- {T['not_shared'].format(area=area)}")
            continue
        value = ctx.get(key)
        if sid in facts:
            text = facts[sid].text(arabic)
        elif sid == "user-data:checkins" and value:
            text = _checkins_line(value, T, arabic)
        else:
            lines.append(f"- {T['no_data'].format(area=area)}")
            missing.append(T["missing_area"].format(area=area))
            continue
        sources.append(AssistantSource(id=sid, title=title))
        lines.append(f"- {text.rstrip('.')} [{len(sources)}]")

    # real missing data only: a vital sign with no reading today
    for v in ctx.get("vitals") or []:
        if v.get("quality") == "missing":
            metric = "bp" if str(v.get("metric", "")).startswith("bp_") else v.get("metric")
            if metric in METRIC_NAMES:
                item = T["missing_vital"].format(name=METRIC_NAMES[metric][1 if arabic else 0])
                item = item[:1].upper() + item[1:]
                if item not in missing:  # bp_sys + bp_dia: one item
                    missing.append(item)
    answer, sources = cited_only(T["head"] + "\n\n" + "\n".join(lines), sources)
    return answer, sources, missing
