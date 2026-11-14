"""Safety filter that runs BEFORE the model. A match means a fixed reply: nothing goes to Ollama.

- medication: medicine/dose words in English and Arabic, every medicine name in the on-board
  resources (read from the monitoring service), and a static list of common generic + brand
  names in English and Arabic (medicine_names.json). "Radiation dose" questions are not medication.
- diagnosis: explicit requests for a diagnosis.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

RefusalReason = Literal["medication", "diagnosis"]

# ---- English -------------------------------------------------------------------
_EN_MEDICATION = re.compile(
    r"\b("
    r"medications?|medicines?|medicated|meds|drugs?|pills?|tablets?|capsules?|prescriptions?|prescribed?|"
    r"doses?|dosages?|dosing|overdose|mg|mcg|milligrams?|micrograms?|ml of|"
    r"painkillers?|pain ?killers?|analgesics?|antibiotics?|antihistamines?|sedatives?|sleeping pills?|"
    r"sleep aids?|stimulants?|injections?|injectables?|ointments?|creams?|eye ?drops|nasal sprays?|"
    # "take" only in a medicine sense ("how long does it take" must pass)
    r"(should|can|could|may|must) i (take|use) (something|anything|some|more|another|any)|"
    r"what (should|can|could) i (take|use)(?= *[?.!]|$| for| to| when| if)|how (much|many|often) (should|can|do) i take|"
    r"take (one|two|some|another|more|\d+) (pills?|tablets?|capsules?|doses?)|taking (it|them|this|that) (for|with|before|after)"
    r")\b",
    re.I,
)
_EN_DIAGNOSIS = re.compile(
    r"\b(diagnos\w*|what (illness|disease|condition|disorder|infection) (do|might|could) i have|"
    r"do i have (a |an )?(disease|illness|infection|disorder|cancer|condition))\b",
    re.I,
)

# ---- Arabic (matched on normalised text: no diacritics, unified alef/ya/ta marbuta) -----
# A word may carry the usual attached prefixes (و، ف، ب، ل، ال، ...).
# Boundaries use Arabic letters only (U+0621..U+064A), so punctuation such as "؟" ends a word.
_AR_PREFIX = r"(?:^|[^ء-ي])(?:و|ف|ب|ل|ك)?(?:ال|لل)?"
_AR_END = r"(?=$|[^ء-ي])"
_AR_MEDICATION_STEMS = [
    "دواء", "دوا", "دوائي", "ادويه", "ادوية", "علاج دوائي", "جرعه", "جرعتي", "جرعات", "كم حبه", "حبوب", "حبات",
    "قرص", "اقراص",
    "كبسوله", "كبسولات", "ملغ", "مغ", "ملغم", "مليغرام", "ميليغرام", "وصفه", "روشته", "مسكن", "مسكنات",
    "مضاد حيوي", "مضادات حيويه", "منوم", "منومات", "ابره", "حقنه", "مرهم", "قطره",
    "اخذ", "اخد", "باخد", "بوخد", "اخده", "اخذه", "اخدها", "اخذها", "اخدهم", "اخذهم", "باخده", "بوخده",
    "اتناول", "تناول", "بتناول", "اتناوله", "اتناولها",
]
_AR_DIAGNOSIS_STEMS = ["تشخيص", "شخص لي", "شخصلي", "شو مرضي", "ما مرضي", "هل عندي مرض", "عندي مرض"]


def _normalise_ar(text: str) -> str:
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    text = text.replace("ـ", "")  # tatweel
    for a in "أإآٱ":
        text = text.replace(a, "ا")
    return text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")


def _ar_pattern(stems: list[str]) -> re.Pattern[str]:
    norm = sorted({_normalise_ar(s) for s in stems}, key=len, reverse=True)
    return re.compile(_AR_PREFIX + "(" + "|".join(re.escape(s) for s in norm) + ")" + _AR_END)


_AR_MEDICATION = _ar_pattern(_AR_MEDICATION_STEMS)
_AR_DIAGNOSIS = _ar_pattern(_AR_DIAGNOSIS_STEMS)

# words in resource names that describe the form, not the medicine
_FORM_WORDS = {"tablets", "tablet", "capsules", "capsule", "nasal", "spray", "cream", "drops", "eye",
               "lubricating", "solution", "oral", "topical", "gel"}


def medicine_terms() -> set[str]:
    """Medicine names from the on-board resources (monitoring service), e.g. 'ibuprofen', 'acetaminophen'."""
    from server.features.monitoring.router import list_resources  # existing service, read only

    terms: set[str] = set()
    try:
        resources = list_resources(kind="medicine")
    except Exception:  # noqa: BLE001  DB not ready: keyword filter still applies
        return terms
    for r in resources:
        name = r.name.lower()
        for word in re.findall(r"[a-z][a-z\-]{3,}", name):
            if word not in _FORM_WORDS:
                terms.add(word)
    return terms


_NAMES_PATH = Path(__file__).with_name("medicine_names.json")


@lru_cache
def static_medicine_names() -> tuple[frozenset[str], re.Pattern[str]]:
    """(English names, compiled Arabic pattern) from medicine_names.json."""
    data = json.loads(_NAMES_PATH.read_text(encoding="utf-8"))
    return frozenset(n.lower() for n in data["en"]), _ar_pattern(data["ar"])


# "Dose" also means radiation dose (mSv), which is a normal question about the references.
_RADIATION_DOSE_EN = re.compile(
    r"\b((radiation|effective|career|absorbed|equivalent|cumulative|annual|daily|total|neutron|solar|space) doses?|"
    r"doses? (limits?|rates?|equivalents?|of radiation|from radiation)|dosimetr\w*|dosimeters?)\b",
    re.I,
)
_RADIATION_DOSE_AR = re.compile(r"جرع(ه|ات) (ال)?(اشعاع|اشعاعيه)")


def _strip_radiation_dose(q: str, ar: str) -> tuple[str, str]:
    return _RADIATION_DOSE_EN.sub(" ", q), _RADIATION_DOSE_AR.sub(" ", ar)


def mentions_medicine_name(text: str, terms: Optional[set[str]] = None) -> bool:
    """Any medicine name: on-board resources + the static EN/AR list (used on questions and answers)."""
    en_static, ar_pattern = static_medicine_names()
    tl = text.lower()
    for term in set(en_static) | (terms if terms is not None else medicine_terms()):
        if re.search(rf"\b{re.escape(term)}\b", tl):
            return True
    return bool(ar_pattern.search(_normalise_ar(text)))


def check_question(question: str, terms: Optional[set[str]] = None) -> Optional[RefusalReason]:
    """Return the refusal reason if the question must not reach the model, else None."""
    q = question.strip()
    ar = _normalise_ar(q)
    q_kw, ar_kw = _strip_radiation_dose(q, ar)
    if _EN_MEDICATION.search(q_kw) or _AR_MEDICATION.search(ar_kw):
        return "medication"
    if mentions_medicine_name(q, terms):
        return "medication"
    if _EN_DIAGNOSIS.search(q) or _AR_DIAGNOSIS.search(ar):
        return "diagnosis"
    return None


def is_arabic(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum("؀" <= c <= "ۿ" for c in letters) / len(letters) > 0.3


REFUSAL_TEXT: dict[str, dict[str, str]] = {
    "medication": {
        "en": ("I can't give advice about medicines or doses. This question needs the crew medical officer "
               "(CMO), who can review it with the flight surgeon during the next comm window. "
               "You can add it to the report for the CMO below."),
        "ar": ("ما بقدر أعطي نصيحة عن الأدوية أو الجرعات. هاد السؤال لازم يراجعه الضابط الطبي للطاقم (CMO) "
               "مع جرّاح الطيران بنافذة الاتصال الجاية. فيك تضيف السؤال لتقرير الـ CMO تحت."),
    },
    "diagnosis": {
        "en": ("I can't give a diagnosis. I can only explain what your data shows and list possible factors "
               "(a possible link, not a confirmed cause). Please raise this with the CMO."),
        "ar": ("ما بقدر أعطي تشخيص. بقدر بس أشرح شو بتبيّن بياناتك وأذكر عوامل محتملة "
               "(ارتباط محتمل، مش سبب مؤكد). احكي مع الـ CMO عن هالموضوع."),
    },
}


def refusal_text(reason: RefusalReason, question: str) -> str:
    return REFUSAL_TEXT[reason]["ar" if is_arabic(question) else "en"]
