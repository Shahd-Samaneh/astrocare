"""Template answer built from the latest Alert, used when the local model is off, fails or times out."""
from __future__ import annotations

from . import store
from .models import AssistantSource

_LABELS = {
    "en": {
        "intro": "The local model is not available right now, so this is the template explanation of your latest alert.",
        "alert": "Alert", "changed": "What changed", "data": "Data used", "missing": "Missing data",
        "factors": "Possible factors (possible link, not a confirmed cause)", "next": "Next steps",
        "locked": "needs CMO review", "none": "none", "readings": "reading(s)",
        "no_alert": "The local model is not available right now, and there is no alert to explain. Try again in a moment.",
        "missing_model": "Local model unavailable: this is a template answer, not an answer to your exact question",
    },
    "ar": {
        "intro": "الموديل المحلي مش متاح هلق، فهاد شرح جاهز (قالب) لآخر تنبيه عندك.",
        "alert": "التنبيه", "changed": "شو تغيّر", "data": "البيانات المستخدمة", "missing": "بيانات ناقصة",
        "factors": "عوامل محتملة (ارتباط محتمل، مش سبب مؤكد)", "next": "الخطوات الجاية",
        "locked": "بحاجة لمراجعة الـ CMO", "none": "ما في", "readings": "قراءة",
        "no_alert": "الموديل المحلي مش متاح هلق، وما في تنبيه لشرحه. جرّب كمان شوي.",
        "missing_model": "الموديل المحلي مش متاح: هاد جواب من قالب، مش جواب لسؤالك بالضبط",
    },
}


def build_fallback(alert: dict | None, *, arabic: bool) -> tuple[str, list[AssistantSource], list[str]]:
    """Return (answer, sources, missing) from the alert's fields."""
    L = _LABELS["ar" if arabic else "en"]
    if not alert:
        return L["no_alert"], [], [L["missing_model"]]

    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items) if items else f"- {L['none']}"

    steps = []
    for s in alert.get("nextSteps") or []:
        # a locked step may name a medicine: never show it from the assistant
        steps.append(f"({L['locked']})" if s.get("lockedForCMO") else s.get("text", ""))
    data_used = alert.get("dataUsed") or []

    answer = "\n\n".join([
        L["intro"],
        f"**{L['alert']} {alert.get('ruleId')}: {alert.get('title')}** [1]",
        f"**{L['changed']}:** {alert.get('whatChanged')} [1]",
        f"**{L['data']}:** {len(data_used)} {L['readings']}",
        f"**{L['missing']}:**\n{bullets(alert.get('missing') or [])}",
        f"**{L['factors']}:**\n{bullets(alert.get('possibleFactors') or [])}",
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
    return answer, sources, [L["missing_model"], *(alert.get("missing") or [])]
