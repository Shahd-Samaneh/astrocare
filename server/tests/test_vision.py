"""Vision self-check (no sensor for SANS): GET/POST /api/vision/checks, comparison with the
baseline, rule R-VIS-01, the Today tile, the seed and the page's accessibility basics.

Tests that write checks use their own throwaway DB so the shared session DB is untouched.
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.core.config import REFERENCES_DIR, has_real_source, iso, thresholds, utcnow

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "app" / "src" / "features" / "monitoring" / "pages" / "Vision.tsx"
PAGE_CSS = PAGE.with_suffix(".module.css")


@pytest.fixture
def vc():
    """A client on a freshly seeded throwaway DB (rules already run, as on startup)."""
    old = os.environ.get("ASTROCARE_DB_PATH")
    os.environ["ASTROCARE_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="astrocare-vision-")) / "vision.db")
    from server.core.seed import seed
    from server.main import app
    try:
        seed(force=True)
        with TestClient(app) as c:
            yield c
    finally:
        if old is None:
            os.environ.pop("ASTROCARE_DB_PATH", None)
        else:
            os.environ["ASTROCARE_DB_PATH"] = old


def _check(eye: str, line: int, grid: bool = False, **kw) -> dict:
    return {"eye": eye, "nearVisionSmallestLine": line, "amslerChanged": grid, **kw}


def _vis_alerts(c) -> list[dict]:
    return [a for a in c.get("/api/alerts").json() if a["ruleId"] == "R-VIS-01" and a["status"] != "closed"]


def _tile(c) -> dict:
    return next(s for s in c.get("/api/body-systems").json() if s["id"] == "vision")


# ---- seed / reseed ---------------------------------------------------------------------
def test_seed_has_a_baseline_and_a_repeat_with_no_change(client):
    checks = client.get("/api/vision/checks?n=10").json()
    assert [c["id"] for c in checks] == ["vis-137", "vis-130"]  # newest first
    assert all(c["source"] == "simulated" and c["eye"] == "both" and c["amslerChanged"] is False for c in checks)
    assert checks[0]["nearVisionSmallestLine"] == checks[1]["nearVisionSmallestLine"]
    s = client.get("/api/vision/summary").json()
    assert (s["status"], s["changed"], s["result"]) == ("stable", False, "Same as baseline")
    assert (s["baselineMissionDay"], s["lastMissionDay"]) == (130, 137)
    assert _vis_alerts(client) == []


def test_reseed_seeds_exactly_two_checks_again(vc):
    from server.core import db
    from server.core.seed import seed
    vc.post("/api/vision/checks", json=_check("left", 3, True))
    assert db.count("vision_checks") == 3
    seed(force=True)
    assert sorted(r["id"] for r in db.query("vision_checks")) == ["vis-130", "vis-137"]


# ---- API ---------------------------------------------------------------------------------
def test_post_one_check_then_get(vc):
    r = vc.post("/api/vision/checks", json=_check("right", 8, notes="  same lamp as usual "))
    assert r.status_code == 201
    body = r.json()
    assert body["id"].startswith("vis-") and body["source"] == "self" and body["notes"] == "same lamp as usual"
    got = vc.get("/api/vision/checks?n=1").json()
    assert [g["id"] for g in got] == [body["id"]]
    assert len(vc.get("/api/vision/checks?n=10").json()) == 3


def test_post_a_session_list(vc):
    r = vc.post("/api/vision/checks", json=[_check("left", 8), _check("right", 9)])
    assert r.status_code == 201
    assert [c["eye"] for c in r.json()] == ["left", "right"]


@pytest.mark.parametrize("bad", [
    _check("left", 0), _check("left", 11), _check("middle", 5), {"eye": "left", "nearVisionSmallestLine": 5},
])
def test_post_rejects_invalid_checks(vc, bad):
    assert vc.post("/api/vision/checks", json=bad).status_code == 422


# ---- change detection + rule ------------------------------------------------------------
def test_no_change_keeps_stable_and_no_alert(vc):
    vc.post("/api/vision/checks", json=[_check("left", 7), _check("right", 8)])  # 1 line: below the trial value
    s = vc.get("/api/vision/summary").json()
    assert (s["status"], s["result"]) == ("stable", "Same as baseline")
    assert _vis_alerts(vc) == []
    assert _tile(vc)["status"] == "stable"


def test_line_drop_of_two_is_a_change_and_fires_the_rule(vc):
    vc.post("/api/vision/checks", json=[_check("left", 6), _check("right", 8)])
    s = vc.get("/api/vision/summary").json()
    assert s["status"] == "review" and s["changed"] is True
    assert s["changes"] == ["Changed since baseline: smallest readable line moved from 8 to 6 (left eye)"]
    left = next(e for e in s["eyes"] if e["eye"] == "left")
    assert left["baseline"]["id"] == "vis-130" and left["linesMoved"] == 2 and left["linesChanged"] is True

    (alert,) = _vis_alerts(vc)
    assert alert["level"] == "info"
    assert alert["sources"][0] == "nasa-hrp-risks"
    # the 5 sections
    assert "moved from 8 to 6 (left eye)" in alert["whatChanged"] and "does not diagnose" in alert["whatChanged"]
    assert "vis-130" in alert["dataUsed"]
    assert any("eye exam" in m for m in alert["missing"])
    assert alert["possibleFactors"]
    assert [s["text"] for s in alert["nextSteps"]] == ["Repeat the check tomorrow", "Add to report for the CMO"]

    tile = _tile(vc)
    assert tile["status"] == "review" and tile["alertId"] == alert["id"]
    assert tile["text"].startswith("Self-check · last mission day ")


def test_grid_change_is_a_change(vc):
    vc.post("/api/vision/checks", json=[_check("left", 8), _check("right", 8, grid=True)])
    s = vc.get("/api/vision/summary").json()
    assert s["changes"] == ["Grid changes reported (right eye)"]
    assert len(_vis_alerts(vc)) == 1


def test_better_line_is_not_a_change(vc):
    vc.post("/api/vision/checks", json=[_check("left", 10), _check("right", 10)])
    assert vc.get("/api/vision/summary").json()["changed"] is False
    assert _vis_alerts(vc) == []


def test_one_open_alert_only(vc):
    vc.post("/api/vision/checks", json=_check("left", 5))
    vc.post("/api/vision/checks", json=_check("left", 4))
    assert len(_vis_alerts(vc)) == 1


def test_no_check_in_due_days_is_self_check_due(vc):
    from server.core import db
    from server.features.monitoring.vision import body_system_tile, vision_summary
    db.update("vision_checks", "vis-137", {"ts": iso(utcnow() - timedelta(days=20))})
    db.update("vision_checks", "vis-130", {"ts": iso(utcnow() - timedelta(days=27))})
    s = vision_summary()
    assert (s.status, s.due) == ("no_data", True)
    status, _text, label = body_system_tile()
    assert (status, label) == ("no_data", "Self-check due")


def test_no_checks_at_all(vc):
    from server.core import db
    with db.connect() as conn:
        conn.execute("DELETE FROM vision_checks")
    s = vc.get("/api/vision/summary").json()
    assert (s["status"], s["result"]) == ("no_data", "No self-check yet")
    assert (_tile(vc)["text"], _tile(vc)["statusLabel"]) == ("No self-check yet", "Self-check due")


# ---- thresholds and source --------------------------------------------------------------
def test_thresholds_are_trial_values():
    t = thresholds()
    drop, due = t["vision_line_drop_min"], t["vision_check_due_days"]
    assert (drop.value, drop.unit, due.value, due.unit) == (2, "lines", 14, "d")
    for entry in (drop, due):
        assert "trial value (team decision)" in entry.note
        assert not has_real_source(entry)  # a team decision, not a NASA number
    assert "references/nasa-hrp-risks.txt" in drop.source


def test_source_title_comes_from_the_reference(client):
    s = client.get("/api/vision/summary").json()
    head = (REFERENCES_DIR / "nasa-hrp-risks.txt").read_text(encoding="utf-8").splitlines()
    assert head[0] == f"title: {s['sourceTitle']}" and s["sourceRef"] == "nasa-hrp-risks"
    assert "Neuro-ocular Syndrome (SANS)" in "\n".join(head)
    assert s["disclaimer"] == ("A self-check to notice changes. It does not diagnose. "
                               "Changes go to the CMO for proper eye exams.")
    assert "diagnos" not in s["why"].lower()


# ---- page accessibility (static checks; the app has no DOM test runner) -------------------
def test_page_buttons_and_options_are_at_least_44px():
    tokens = (ROOT / "app" / "src" / "shared" / "styles" / "tokens.css").read_text(encoding="utf-8")
    assert re.search(r"--tap-min:\s*44px", tokens)
    button_css = (ROOT / "app" / "src" / "shared" / "components" / "Button.module.css").read_text(encoding="utf-8")
    assert "min-height: var(--tap-min)" in button_css
    css = PAGE_CSS.read_text(encoding="utf-8")
    option = re.search(r"\.option \{([^}]*)\}", css).group(1)
    assert "min-height: var(--tap-min)" in option and "min-width: var(--tap-min)" in option
    tsx = PAGE.read_text(encoding="utf-8")
    assert "<button" not in tsx  # every button is the shared Button (>= 44 px)


def test_page_controls_are_labelled():
    tsx = PAGE.read_text(encoding="utf-8")
    # every radio sits inside a <label>, in a fieldset with a legend
    assert tsx.count('type="radio"') == 2 and tsx.count("<fieldset") == 2 and tsx.count("<legend>") == 2
    assert tsx.count("aria-label={`${label}, line ${i + 1}`}") == 1
    assert 'htmlFor="vision-notes"' in tsx and 'id="vision-notes"' in tsx
    assert 'role="img"' in tsx and "aria-label={`Amsler grid" in tsx
    assert "Do any lines look wavy, blurred or missing?" in tsx
    assert "Add to report for the CMO" in tsx and "Ask the assistant" in tsx
    assert "sourceFeature: 'monitoring'" in tsx and "kind: 'note'" in tsx


def test_nav_and_route_exist():
    nav = (ROOT / "app" / "src" / "shared" / "components" / "SideNav.tsx").read_text(encoding="utf-8")
    assert "{ to: '/vision', label: 'Vision check', icon: Eye }" in nav
    assert nav.index("'/bone'") < nav.index("'/vision'") < nav.index("label: 'Support'")
    routes = (ROOT / "app" / "src" / "routes.tsx").read_text(encoding="utf-8")
    assert "{ path: 'vision', element: <Vision /> }" in routes


def test_card_has_as_many_lines_as_the_backend_accepts():
    from server.features.monitoring.vision import NEAR_VISION_LINES
    tsx = PAGE.read_text(encoding="utf-8")
    block = tsx.split("const NEAR_VISION_LINES")[1].split("];")[0]
    assert len(re.findall(r"\{ px: \d+, text:", block)) == NEAR_VISION_LINES
    sizes = [int(x) for x in re.findall(r"px: (\d+)", block)]
    assert sizes == sorted(sizes, reverse=True) and len(set(sizes)) == len(sizes)  # strictly decreasing
