"""Arabic number + noun agreement for the fixed texts (template, fixed facts).

    ar_count(1, "ليلة", "ليلتين", "ليالي")   -> "ليلة واحدة"
    ar_count(2, ...)                         -> "ليلتين"
    ar_count(5, ...)                         -> "5 ليالي"     (3–10: plural)
    ar_count(14, ...)                        -> "14 ليلة"     (11+: singular)
    ar_count(0, ...)                         -> "0 ليلة"
"""
from __future__ import annotations

# noun -> (singular, dual, plural 3–10)
NOUNS = {
    "night": ("ليلة", "ليلتين", "ليالي"),
    "test": ("اختبار", "اختبارين", "اختبارات"),
    "reading": ("قراءة", "قراءتين", "قراءات"),
    "hour": ("ساعة", "ساعتين", "ساعات"),
    "lapse": ("هفوة", "هفوتين", "هفوات"),
}


def ar_count(n: int | float, singular: str, dual: str, plural: str) -> str:
    n_int = int(n)
    if n_int != n:  # e.g. 6.5 hours: number + singular
        return f"{n:g} {singular}"
    if n_int == 1:
        return f"{singular} واحدة" if singular.endswith("ة") else f"{singular} واحد"
    if n_int == 2:
        return dual
    if 3 <= n_int <= 10:
        return f"{n_int} {plural}"
    return f"{n_int} {singular}"


def ar_n(n: int | float, noun: str) -> str:
    return ar_count(n, *NOUNS[noun])
