"""Fixed facts: numbers the data already gives exactly, computed in code, never by the model.

1. build_facts(ctx)  -> one fact line per data area (sleep, attention, vitals, exercise)
   The prompt shows them as "FIXED FACT: ..." inside each "Your data" source; the model is told
   to repeat them as written and never contradict them.
2. enforce_facts(...) -> after the answer: a sentence about the user's own data that contradicts
   a fact (e.g. "no lapses" when lapses > 0, "heart rate is stale" when it is up to date, a sleep
   duration that is not in the data) is replaced by that fact line, with its citation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .arabic import ar_n

METRIC_NAMES = {
    "heart_rate": ("heart rate", "معدل النبض"),
    "spo2": ("SpO₂", "تشبع الأكسجين"),
    "skin_temp": ("skin temperature", "حرارة الجلد"),
    "bp": ("blood pressure", "ضغط الدم"),
    "resp_rate": ("respiration rate", "معدل التنفس"),
}
_METRIC_RE = {
    "heart_rate": r"heart ?rate|pulse|نبض",
    "spo2": r"spo₂|spo2|oxygen saturation|الأكسجين|الاكسجين",
    "skin_temp": r"skin temp\w*|حرارة الجلد|حراره الجلد",
    "bp": r"blood pressure|\bbp\b|ضغط",
    "resp_rate": r"respirat\w* rate|breathing rate|التنفس",
}


@dataclass
class Fact:
    key: str        # sleep | attention | vitals | exercise
    source_id: str  # the "Your data" source it belongs to
    en: str
    ar: str
    data: dict      # the exact values, used by the contradiction checks

    def text(self, arabic: bool) -> str:
        return self.ar if arabic else self.en


def _hm(minutes: float) -> str:
    return f"{int(minutes // 60)} h {int(round(minutes % 60)):02d} m"


def _vital_groups(vitals: list[dict]) -> dict[str, dict]:
    """metric -> {"quality", "age"}; bp_sys + bp_dia are reported as one 'bp'."""
    out: dict[str, dict] = {}
    for v in vitals:
        m = "bp" if str(v.get("metric", "")).startswith("bp_") else v.get("metric")
        if m in METRIC_NAMES and m not in out:
            out[m] = {"quality": v.get("quality"), "age": v.get("age")}
    return out


def build_facts(ctx: dict) -> dict[str, Fact]:
    facts: dict[str, Fact] = {}
    not_shared = ctx.get("notShared") or []

    s = ctx.get("sleep7d")
    if s and "sleep" not in not_shared:
        durs = s.get("durationsMin") or []
        under = s.get("nightsUnderShort")
        short_h = s.get("shortHours")
        under_en = f"; {under} night(s) under {short_h:g} h" if under is not None and short_h else ""
        under_ar = f"؛ {ar_n(under, 'night')} أقل من {ar_n(short_h, 'hour')}" if under is not None and short_h else ""
        facts["sleep"] = Fact(
            "sleep", "user-data:sleep",
            en=(f"Sleep, last 7 days: {s['nights']} nights recorded; average {s['average']}; "
                f"shortest {s['shortest']}; last night {s['lastNight']}{under_en}."),
            ar=(f"النوم، آخر 7 أيام: {ar_n(s['nights'], 'night')} مسجّلة؛ المعدل {s['average']}؛ "
                f"أقصر ليلة {s['shortest']}؛ الليلة الماضية {s['lastNight']}{under_ar}."),
            data={"durations": durs, "nightsUnder": under, "shortHours": short_h},
        )

    tests = ctx.get("attention7d") or []
    if tests and "attention tests" not in not_shared:
        first, last = tests[0], tests[-1]
        total_lapses = sum(int(t.get("lapses") or 0) for t in tests)
        facts["attention"] = Fact(
            "attention", "user-data:attention",
            en=(f"Attention tests, last 7 days: {len(tests)} tests; latest median reaction time "
                f"{last['medianMs']:.0f} ms (first test in the window: {first['medianMs']:.0f} ms); "
                f"lapses in the latest test: {last.get('lapses') or 0}; lapses over 7 days: {total_lapses}."),
            ar=(f"اختبارات الانتباه، آخر 7 أيام: {ar_n(len(tests), 'test')}؛ آخر متوسط زمن استجابة "
                f"{last['medianMs']:.0f} ms (أول اختبار بالفترة: {first['medianMs']:.0f} ms)؛ "
                f"الهفوات بآخر اختبار: {last.get('lapses') or 0}؛ الهفوات خلال 7 أيام: {total_lapses}."),
            data={"medians": [float(t["medianMs"]) for t in tests if t.get("medianMs") is not None],
                  "latestLapses": int(last.get("lapses") or 0), "totalLapses": total_lapses},
        )

    vit = ctx.get("vitals")
    if vit and "vitals" not in not_shared:
        groups = _vital_groups(vit)
        fresh = [m for m, g in groups.items() if g["quality"] in ("good", "low")]
        stale = [m for m, g in groups.items() if g["quality"] == "stale"]
        missing = [m for m, g in groups.items() if g["quality"] == "missing"]

        def names(ms: list[str], ar: bool, with_age: bool = False) -> str:
            parts = []
            for m in ms:
                n = METRIC_NAMES[m][1 if ar else 0]
                age = groups[m].get("age")
                parts.append(f"{n} ({age})" if with_age and age else n)
            return ", ".join(parts) if parts else ("ما في" if ar else "none")

        facts["vitals"] = Fact(
            "vitals", "user-data:vitals",
            en=(f"Vital signs: up to date: {names(fresh, False)}; stale: {names(stale, False, True)}; "
                f"missing today: {names(missing, False)}."),
            ar=(f"العلامات الحيوية: محدّثة: {names(fresh, True)}؛ قديمة: {names(stale, True, True)}؛ "
                f"ناقصة اليوم: {names(missing, True)}."),
            data={"quality": {m: g["quality"] for m, g in groups.items()}},
        )

    ex = ctx.get("exerciseToday")
    if ex and "exercise" not in not_shared:
        logged = bool(ex.get("logged"))
        planned = ex.get("planned")
        facts["exercise"] = Fact(
            "exercise", "user-data:exercise",
            en=f"Exercise today: planned {planned or 'nothing'}; {'logged' if logged else 'not logged yet'}.",
            ar=f"التمرين اليوم: المخطط {planned or 'ما في'}؛ {'مسجّل' if logged else 'لسا ما تسجّل'}.",
            data={"logged": logged},
        )
    return facts


# ---- contradiction checks ---------------------------------------------------------------
# a sentence must talk about the user's own data before it is checked (reference sentences pass)
_ABOUT_USER = re.compile(r"\b(you|your|latest|last night|this week|averag\w*|recorded)\b|نومك|انت|إنت|معدل|آخر|عندك", re.I)
_SLEEP = re.compile(r"\bsleep\w*|\bslept\b|\bnights?\b|نوم|ليال|ليلة", re.I)
_ATTN = re.compile(r"attention|reaction time|lapses?|\bPVT\b|انتباه|استجابة|هفو", re.I)
_STALE_WORDS = re.compile(r"\bstale\b|outdated|out of date|not (been )?updated|no recent (data|readings?)|قديم", re.I)
# "no recent data" / "not up to date" say stale, not fresh: negated forms don't count
_FRESH_WORDS = re.compile(r"(?<!\bno )(?<!\bnot )(?<!\bno new )\b(up to date|up-to-date|fresh|current|recent)\b|محدّث|محدث", re.I)
_MISSING_WORDS = re.compile(r"\bmissing\b|no reading|ناقص", re.I)
_NO_LAPSES = re.compile(r"\bno (attention )?lapses?\b|without (any )?lapses?|zero lapses?|0 lapses?|"
                        r"ما في هفوات|بدون هفوات|لا يوجد هفوات|لا هفوات", re.I)
_N_LAPSES = re.compile(r"\b(\d+)\s+lapses?\b|(\d+)\s+هفو", re.I)
_MS = re.compile(r"\b(\d{3,4})(?:\s*[-–]\s*(\d{3,4}))?\s*(?:ms|milliseconds?|ملي)", re.I)
_DURATION = re.compile(r"\b(\d{1,2})\s*(?:h|hrs?|hours?|ساعات|ساعة)\b(?:\s*(?:and\s*)?(\d{1,2})\s*(?:m|min|minutes?|دقيقة|دقائق)\b)?", re.I)
_UNDER = re.compile(r"\b(\d+|one|two|three|four|five|six|seven)\s+nights?\s+(?:under|below|less than|shorter than)\b", re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_NEGATED = re.compile(r"\b(not|isn't|aren't|wasn't|no longer)\b|مش|ليس", re.I)


def _contradicts_sleep(sent: str, f: Fact) -> bool:
    if not _SLEEP.search(sent):
        return False
    if _STALE_WORDS.search(sent):  # sleep sessions are not readings: never "stale"
        return True
    durs = f.data["durations"]
    allowed = set(durs) | {sum(durs) / len(durs), min(durs)} if durs else set()
    for m in _DURATION.finditer(sent):
        minutes = int(m.group(1)) * 60 + int(m.group(2) or 0)
        if allowed and all(abs(minutes - a) > 5 for a in allowed):
            if f.data.get("shortHours") and minutes == f.data["shortHours"] * 60:
                continue  # "under 6 h" names the threshold, not a night
            return True
    m = _UNDER.search(sent)
    if m and f.data.get("nightsUnder") is not None:
        n = int(m.group(1)) if m.group(1).isdigit() else _WORDNUM[m.group(1).lower()]
        if n != f.data["nightsUnder"]:
            return True
    return False


def _contradicts_attention(sent: str, f: Fact) -> bool:
    if not _ATTN.search(sent):
        return False
    if _NO_LAPSES.search(sent) and f.data["totalLapses"] > 0:
        return True
    for m in _N_LAPSES.finditer(sent):
        n = int(m.group(1) or m.group(2))
        if n not in (f.data["latestLapses"], f.data["totalLapses"]):
            return True
    medians = f.data["medians"]
    for m in _MS.finditer(sent):
        for g in (m.group(1), m.group(2)):
            if g and medians and all(abs(int(g) - v) > 1 for v in medians):
                return True
    return False


def _contradicts_vitals(sent: str, f: Fact) -> bool:
    quality = f.data["quality"]
    for metric, pat in _METRIC_RE.items():
        if metric not in quality or not re.search(pat, sent, re.I):
            continue
        q = quality[metric]
        negated = bool(_NEGATED.search(sent))
        if q in ("good", "low") and (_STALE_WORDS.search(sent) or (_MISSING_WORDS.search(sent) and not negated)):
            return True
        if q == "stale" and _FRESH_WORDS.search(sent) and not negated:
            return True
        if q == "stale" and _MISSING_WORDS.search(sent) and not _STALE_WORDS.search(sent) and not negated:
            return True
    return False


def _contradicts_exercise(sent: str, f: Fact) -> bool:
    if not re.search(r"exercis\w*|workout|تمرين", sent, re.I):
        return False
    said_done = re.search(r"\b(completed|did|done|logged|finished)\b", sent, re.I) and not _NEGATED.search(sent)
    said_not = re.search(r"\b(not|haven't|hasn't|didn't|no)\b.*\b(complete|completed|done|logged|exercise)\b", sent, re.I)
    return bool((said_done and not f.data["logged"]) or (said_not and f.data["logged"]))


_CHECKS = {"sleep": _contradicts_sleep, "attention": _contradicts_attention,
           "vitals": _contradicts_vitals, "exercise": _contradicts_exercise}

# sentences: don't split "33.9" or "6.2"
SENTENCE = re.compile(r"(?:[^.!?؟\n]|(?<=\d)\.(?=\d))+[.!?؟]?")


def contradicted_facts(sentence: str, facts: dict[str, Fact]) -> list[Fact]:
    if not _ABOUT_USER.search(sentence):
        return []
    return [f for k, f in facts.items() if _CHECKS[k](sentence, f)]
