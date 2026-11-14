"""Number + noun agreement for the fixed texts (template, fixed facts), Arabic and English.

    en_n(1, "night") -> "1 night"      en_n(2, "night") -> "2 nights"

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
    "checkin": ("تسجيل", "تسجيلين", "تسجيلات"),
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


# English: noun -> plural (when it is not just noun + "s")
_EN_PLURAL = {"check-in": "check-ins"}


def en_n(n: int | float, noun: str) -> str:
    """'1 night', '2 nights', '0 nights', '1.5 hours'."""
    word = noun if n == 1 else _EN_PLURAL.get(noun, noun + "s")
    return f"{n:g} {word}"
