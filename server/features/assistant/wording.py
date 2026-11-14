"""Medical wording on the model's answer: no cause claims about the user's data.

In a sentence about the user's own data or alerts, cause wording becomes "possible factor" /
"possibly linked to", and the sentence gets "(a possible link, not a confirmed cause)".
Sentences from the references ("Radiation causes DNA damage [5].") are left alone.
"""
from __future__ import annotations

import re

from .facts import SENTENCE

CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

_ABOUT_USER = re.compile(
    r"\b(you|your|yours|latest|last night|this week|averag\w*|recorded|(?:the|this|that) alert|(?:the|these) readings?)\b"
    r"|نومك|انت|إنت|عندك|بياناتك|التنبيه|تنبيه|قراءاتك|قراءة",
    re.I,
)

TAG_EN = "a possible link, not a confirmed cause"
TAG_AR = "ارتباط محتمل، مش سبب مؤكد"

# protected phrases (they already say the right thing)
_PROTECT = re.compile(r"not a confirmed cause|not confirmed causes?|confirmed causes?|مش سبب مؤكد|ليس سببا? مؤكدا?|ليس سببًا مؤكدًا|سبب مؤكد", re.I)

# order matters: longer phrases first
_EN_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:the |a )?(?:main |likely |probable |real |actual |root |exact |primary )?causes (?:of|for|behind)\b", re.I), "possible factors in"),
    (re.compile(r"\b(?:the |a )?(?:main |likely |probable |real |actual |root |exact |primary )?cause (?:of|for|behind)\b", re.I), "a possible factor in"),
    (re.compile(r"\b(?:possible|potential|likely|probable) causes\b", re.I), "possible factors"),
    (re.compile(r"\b(?:possible|potential|likely|probable) cause\b", re.I), "possible factor"),
    (re.compile(r"\b(is|are|was|were|be|been) (?:likely |probably |possibly |most likely )?caused by\b", re.I), r"\1 possibly linked to"),
    (re.compile(r"\bcaused by\b", re.I), "possibly linked to"),
    (re.compile(r"\bbecause of\b", re.I), "possibly linked to"),
    (re.compile(r"\bdue to\b", re.I), "possibly linked to"),
    (re.compile(r"\b(can|may|might|could|will|would|to) cause\b", re.I), r"\1 contribute to"),
    (re.compile(r"\bcaused\b", re.I), "possibly contributed to"),
    (re.compile(r"\bcausing\b", re.I), "possibly contributing to"),
    (re.compile(r"\bcauses\b", re.I), "possible factors"),
    (re.compile(r"\bcause\b", re.I), "possible factor"),
]
_AR_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"بسبب"), "بارتباط محتمل مع"),
    (re.compile(r"(?:ال)?[أا]سباب"), "العوامل المحتملة"),
    (re.compile(r"السبب"), "العامل المحتمل"),
    (re.compile(r"[يت]سبب"), "ممكن يساهم ب"),
    (re.compile(r"(?<![ء-ي])سبب(?![ء-ي])"), "عامل محتمل"),
]


def is_about_user(sentence: str, cited: set[int], user_nums: set[int]) -> bool:
    """About the user's own data / alerts: it cites one of them, or talks to the user."""
    return bool(cited & user_nums) or bool(_ABOUT_USER.search(CITE.sub("", sentence)))


def _cited(sentence: str) -> set[int]:
    return {int(n) for m in CITE.finditer(sentence) for n in m.group(1).split(",")}


def _add_tag(sentence: str, tag: str) -> str:
    """Insert ' (tag)' before trailing citations and the final punctuation."""
    m = re.search(r"(\s*(?:\[[\d,\s]+\]\s*)*)([.!?؟]?)(\s*)$", sentence)
    head, cites, punct, ws = sentence[: m.start()], m.group(1), m.group(2), m.group(3)
    return f"{head} ({tag}){cites}{punct}{ws}"


def soften_sentence(sentence: str, *, arabic: bool) -> str:
    protected: list[str] = []

    def keep(m: re.Match[str]) -> str:
        protected.append(m.group(0))
        return f"\x00{len(protected) - 1}\x00"

    s = _PROTECT.sub(keep, sentence)
    changed = False
    for pat, rep in _EN_RULES + _AR_RULES:
        s, n = pat.subn(rep, s)
        changed = changed or n > 0
    for i, p in enumerate(protected):
        s = s.replace(f"\x00{i}\x00", p)
    if not changed:
        return sentence
    has_tag = TAG_EN in s.lower() or TAG_AR in s or "not a confirmed cause" in s.lower()
    if not has_tag:
        s = _add_tag(s, TAG_AR if arabic else TAG_EN)
    # keep a capital letter at the start
    lead = len(s) - len(s.lstrip(" -*•"))
    if lead < len(s) and sentence.lstrip(" -*•")[:1].isupper():
        s = s[:lead] + s[lead].upper() + s[lead + 1:]
    return s


def soften_causes(text: str, user_nums: set[int], *, arabic: bool) -> str:
    """Apply soften_sentence to every sentence about the user's data / alerts."""
    def fix(m: re.Match[str]) -> str:
        sent = m.group(0)
        if not is_about_user(sent, _cited(sent), user_nums):
            return sent
        return soften_sentence(sent, arabic=arabic)

    return SENTENCE.sub(fix, text)
