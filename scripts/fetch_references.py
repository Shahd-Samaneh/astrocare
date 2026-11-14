"""DEV-TIME ONLY: download the NASA/CSA reference pages once and save them as plain text.

The running app never calls this and never opens these URLs. It reads only the saved
references/<id>.txt files (the URLs in their headers are citation data).

    node scripts/py.mjs scripts/fetch_references.py            # fetch every missing reference
    node scripts/py.mjs scripts/fetch_references.py --force    # re-fetch all
    node scripts/py.mjs scripts/fetch_references.py nasa-bone-risk   # only these ids

Output: references/<id>.txt starting with
    title: ...
    url: ...
    id: ...
followed by a blank line and the main article text. Pages that fail are listed at the end;
paste their text by hand in the same format. The PDF needs `pip install pypdf` (dev only).
"""
from __future__ import annotations

import html
import io
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "references"

# id -> (url, fallback title). Ids match the Daily pair's sources.py.
REFERENCES: dict[str, tuple[str, str]] = {
    # proposal references
    "ntrs-cds-market-survey": ("https://ntrs.nasa.gov/citations/20250000388",
                               "Exploration Medical IPT Clinical Decision Support Market Survey (HRP IWS 2025)"),
    "ntrs-cdss-conops": ("https://ntrs.nasa.gov/citations/20220017856",
                         "Exploration Medical Capability CDSS Concept of Operations (HRP-48033, 2021)"),
    "nasa-hrp-sleep-risk": ("https://www.nasa.gov/directorates/esdmd/hhp/risk-of-performance-decrements-and-adverse-health-outcomes-resulting-from-sleep-loss-circadian-desynchronization-and-work-overload/",
                            "Risk of Performance Decrements and Adverse Health Outcomes Resulting from Sleep Loss, Circadian Desynchronization, and Work Overload"),
    "nasa-hrp-bmed-risk": ("https://ntrs.nasa.gov/citations/20250001454",
                           "Risk of Adverse Cognitive or Behavioral Conditions and Psychiatric Disorders (evidence report, 2025)"),
    "ntrs-ai-cdss-osce": ("https://ntrs.nasa.gov/citations/20250002755",
                          "Objective Structured Clinical Examination of an AI Clinical Decision Support Tool (2025)"),
    "ntrs-olfactory-vr-stress": ("https://ntrs.nasa.gov/citations/20260005215",
                                 "Olfactory-enhanced Virtual Reality for Stress Reduction in ICE Environments (2026)"),
    "nasa-osdr": ("https://science.nasa.gov/biological-physical/data/osdr/", "NASA Open Science Data Repository (OSDR)"),
    "csa-bio-monitor": ("https://asc-csa.gc.ca/eng/sciences/astroskin.asp", "CSA Bio-Monitor (Astroskin)"),
    "nasa-pvt-iss": ("https://techport.nasa.gov/projects/23201", "NASA TechPort project 23201 (PVT on ISS)"),
    "google-nasa-cmo-assistant": ("https://cloud.google.com/blog/topics/public-sector/how-google-and-nasa-are-testing-ai-for-medical-care-in-space",
                                  "How Google and NASA are testing AI for medical care in space"),
    # plan references
    "nasa-hrp-hazards": ("https://www.nasa.gov/hrp/hazards/", "NASA HRP: The Human Body in Space (five hazards)"),
    "nasa-hrp-risks": ("https://www.nasa.gov/hrp/risks/", "NASA HRP: Human System Risks"),
    "nasa-hrp-ongoing": ("https://www.nasa.gov/hrp/ongoing-hrp-research/", "NASA HRP: Ongoing Research"),
    "csa-radiation-monitoring": ("https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp",
                                 "CSA: Monitoring radiation to protect astronaut health"),
    "csa-why-science-in-space": ("https://www.asc-csa.gc.ca/eng/iss/science/why-do-we-conduct-science-experiments-in-space.asp",
                                 "CSA: Why do we conduct science experiments in space?"),
    "nasa-ochmo-radiation": ("https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf",
                             "OCHMO Technical Brief: Radiation Protection"),
    "nasa-bone-risk": ("https://www.nasa.gov/reference/risk-of-spaceflight-induced-bone-changes/",
                       "Risk of Spaceflight-Induced Bone Changes"),
}

HEADERS = {"User-Agent": "Mozilla/5.0 (reference-text fetcher; dev-time, one-off)", "Accept-Language": "en"}
MIN_WORDS = 120  # below this the page probably needs JavaScript: treat as failed


# ---- HTML -> main text ------------------------------------------------------------
class _MainText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "button", "iframe"}
    BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "li", "td", "th", "blockquote", "figcaption", "dd", "dt"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_main = 0
        self.blocks: list[tuple[bool, str]] = []  # (inside <main>/<article>, text)
        self.cur: list[str] = []
        self.title = ""
        self.og_title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property") == "og:title":
            self.og_title = a.get("content") or ""
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag in ("main", "article"):
            self.in_main += 1
        if tag in self.BLOCK or tag == "br":
            self._flush()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag in self.BLOCK:
            self._flush()
        if tag in ("main", "article") and self.in_main:
            self._flush()
            self.in_main -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skip_depth:
            self.cur.append(data)

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.cur)).strip()
        self.cur = []
        if text:
            self.blocks.append((self.in_main > 0, text))


def html_to_text(raw: str) -> tuple[str, str]:
    p = _MainText()
    p.feed(raw)
    p.close()
    main = [t for inside, t in p.blocks if inside]
    blocks = main if len(" ".join(main).split()) >= MIN_WORDS else [t for _, t in p.blocks]
    # drop very short boilerplate lines (menus, share buttons) and consecutive duplicates
    out: list[str] = []
    for b in blocks:
        if len(b.split()) < 4 and not b.endswith((".", ":", "?")):
            continue
        if out and out[-1] == b:
            continue
        out.append(b)
    title = (p.og_title or p.title).strip()
    return title, "\n\n".join(_trim_boilerplate(out))


# The article ends where these "more links" / page-footer lines start.
_STOP = re.compile(r"(Keep Exploring$|^Discover More Topics From NASA|^Date modified:|^Explore more:|^Linkedin:)")
_BYLINE_READ = re.compile(r"•\s*\d+-minute read$")  # blog "related posts": headline, then this byline
_AGE = re.compile(r"^article \d+ \w+ ago$", re.I)  # NASA "article 9 months ago" label


def _trim_boilerplate(blocks: list[str]) -> list[str]:
    blocks = [b for b in blocks if not _AGE.match(b)]
    for i, b in enumerate(blocks):
        if _STOP.search(b):
            return blocks[:i]
        if _BYLINE_READ.search(b):
            return blocks[: max(i - 1, 0)]
    return blocks


# ---- special sources ----------------------------------------------------------------
def fetch_ntrs(client: httpx.Client, url: str) -> tuple[str, str]:
    """NTRS pages are rendered with JavaScript; its public JSON API has title + abstract."""
    cid = url.rstrip("/").rsplit("/", 1)[-1]
    r = client.get(f"https://ntrs.nasa.gov/api/citations/{cid}")
    r.raise_for_status()
    d = r.json()
    parts = [d.get("abstract") or ""]
    authors = [a.get("meta", {}).get("author", {}).get("name") for a in d.get("authorAffiliations", [])]
    authors = [a for a in authors if a]
    meta = []
    if authors:
        meta.append("Authors: " + ", ".join(authors))
    if d.get("publications"):
        pub = d["publications"][0]
        if pub.get("publicationDate"):
            meta.append("Published: " + pub["publicationDate"][:10])
    if d.get("stiType"):
        meta.append("Document type: " + str(d["stiType"]).replace("_", " ").title())
    if d.get("keywords"):
        meta.append("Keywords: " + ", ".join(d["keywords"]))
    text = "\n\n".join(m for m in meta + parts if m)
    return html.unescape(d.get("title") or ""), text


def fetch_techport(client: httpx.Client, url: str) -> tuple[str, str]:
    """TechPort pages are rendered with JavaScript; its public JSON API has the text."""
    pid = url.rstrip("/").rsplit("/", 1)[-1]
    r = client.get(f"https://techport.nasa.gov/api/projects/{pid}")
    r.raise_for_status()
    p = r.json().get("project", {})
    parts = []
    if p.get("startDate") or p.get("endDate"):
        parts.append(f"Project dates: {p.get('startDate', '?')} to {p.get('endDate', '?')}")
    for key, label in (("description", "Description"), ("benefits", "Benefits")):
        if p.get(key):
            parts.append(f"{label}:\n{html_to_text(p[key])[1] or p[key]}")
    return p.get("title") or "", "\n\n".join(parts)


def fetch_html(client: httpx.Client, url: str) -> tuple[str, str]:
    try:
        r = client.get(url)
    except httpx.TransportError:
        # asc-csa.gc.ca drops connections on the bare host; the www. host serves the same page
        if "://asc-csa.gc.ca" not in url:
            raise
        r = client.get(url.replace("://asc-csa.gc.ca", "://www.asc-csa.gc.ca"))
    r.raise_for_status()
    return html_to_text(r.text)


def fetch_pdf(client: httpx.Client, url: str) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # dev-only dependency
    except ImportError as e:
        raise RuntimeError("pypdf not installed (dev only: pip install pypdf), or paste the PDF text") from e
    r = client.get(url)
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    pages = [(pg.extract_text() or "").strip() for pg in reader.pages]
    text = "\n\n".join(re.sub(r"[ \t]+", " ", p) for p in pages if p)
    title = (reader.metadata.title if reader.metadata and reader.metadata.title else "") or ""
    return title, text


def fetch_one(client: httpx.Client, ref_id: str, url: str, fallback_title: str) -> int:
    if "ntrs.nasa.gov/citations/" in url:
        title, text = fetch_ntrs(client, url)
        min_words = 40  # an abstract can be short
    elif "techport.nasa.gov/projects/" in url:
        title, text = fetch_techport(client, url)
        min_words = 40
    elif url.lower().endswith(".pdf"):
        title, text = fetch_pdf(client, url)
        min_words = MIN_WORDS
    else:
        title, text = fetch_html(client, url)
        min_words = MIN_WORDS
    words = len(text.split())
    if words < min_words:
        raise RuntimeError(f"only {words} words extracted (page probably needs JavaScript)")
    title = re.sub(r"\s*[|\-–]\s*(NASA|Canadian Space Agency|Google Cloud Blog).*$", "", title).strip() or fallback_title
    header = f"title: {title}\nurl: {url}\nid: {ref_id}\n\n"
    (OUT_DIR / f"{ref_id}.txt").write_text(header + text.strip() + "\n", encoding="utf-8")
    return words


def main(argv: list[str]) -> int:
    force = "--force" in argv
    wanted = [a for a in argv if not a.startswith("--")] or list(REFERENCES)
    OUT_DIR.mkdir(exist_ok=True)
    failed: list[tuple[str, str, str]] = []
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        for ref_id in wanted:
            url, fallback = REFERENCES[ref_id]
            if (OUT_DIR / f"{ref_id}.txt").exists() and not force:
                print(f"  = {ref_id}: exists (use --force to re-fetch)")
                continue
            try:
                words = fetch_one(client, ref_id, url, fallback)
                print(f"  ✓ {ref_id}: {words} words")
            except Exception as e:  # noqa: BLE001  report every failure, keep going
                failed.append((ref_id, url, str(e)[:160]))
                print(f"  ✗ {ref_id}: {str(e)[:160]}")
    if failed:
        print("\nFailed (paste these by hand as references/<id>.txt):")
        for ref_id, url, err in failed:
            print(f"  - {ref_id}  {url}\n      {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
