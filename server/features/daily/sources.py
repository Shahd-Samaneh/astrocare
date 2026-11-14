# Owner: Shahd
"""NASA basis for the Daily features: GET /api/daily/sources.

The URLs live here on the backend only, so the frontend bundle stays free of
remote URLs (offline rule). These are public reference pages we read; listing
them does not mean NASA endorses or reviewed AstroCare.

The ids are shared with the assistant's `references/` (Marah) and with alert
`sources` (R-SLP-01, R-FAT-01).
"""
from __future__ import annotations

from fastapi import APIRouter

from server.core.models import ApiModel

router = APIRouter()


class NasaSource(ApiModel):
    id: str
    org: str
    title: str
    url: str
    why: str


SOURCES: list[NasaSource] = [
    NasaSource(
        id="nasa-hrp-sleep-risk", org="NASA",
        title="NASA HRP: Risk of performance decrements and adverse health outcomes from sleep loss, "
              "circadian desynchronization and work overload",
        url="https://www.nasa.gov/directorates/esdmd/hhp/risk-of-performance-decrements-and-adverse-health-"
            "outcomes-resulting-from-sleep-loss-circadian-desynchronization-and-work-overload/",
        why="NASA lists lost and shifted sleep as a crew health risk, so we watch for runs of short nights.",
    ),
    NasaSource(
        id="nasa-hrp-bmed-risk", org="NASA",
        title="NASA HRP evidence report: Risk of adverse cognitive or behavioral conditions and psychiatric "
              "disorders (NTRS 20250001454)",
        url="https://ntrs.nasa.gov/citations/20250001454",
        why="Mood, stress and thinking speed can drift during long missions, so a short daily self-report "
            "and a reaction test help notice changes early.",
    ),
    NasaSource(
        id="nasa-pvt-iss", org="NASA",
        title="NASA TechPort 23201: Psychomotor Vigilance Test (PVT) on ISS",
        url="https://techport.nasa.gov/projects/23201",
        why="A brief reaction-time test of this kind has been used on the ISS to track alertness, which is "
            "the idea behind our attention check.",
    ),
    NasaSource(
        id="nasa-hrp-hazards", org="NASA",
        title="NASA HRP: 5 Hazards of Human Spaceflight (isolation and confinement; gravity fields)",
        url="https://www.nasa.gov/hrp/hazards/",
        why="Isolation, confinement and changed gravity affect both mood and the body, which is why we "
            "check in daily and keep exercise on the plan.",
    ),
    NasaSource(
        id="nasa-hrp-risks", org="NASA",
        title="NASA HRP: Risks of Human Spaceflight (fitness and musculoskeletal risks)",
        url="https://www.nasa.gov/hrp/risks/",
        why="Lost fitness and muscle strength are known spaceflight risks, so missed exercise days are "
            "worth flagging.",
    ),
    NasaSource(
        id="nasa-bone-risk", org="NASA",
        title="NASA: Risk of spaceflight-induced bone changes",
        url="https://www.nasa.gov/reference/risk-of-spaceflight-induced-bone-changes/",
        why="Bone can weaken in microgravity, and regular loading exercise is one of the main ways to "
            "limit it.",
    ),
    NasaSource(
        id="nasa-hrp-ongoing", org="NASA",
        title="NASA HRP: Ongoing research in space",
        url="https://www.nasa.gov/hrp/ongoing-hrp-research/",
        why="Current NASA studies follow sleep and activity with wrist-worn devices, the same kind of data "
            "our sleep log uses.",
    ),
]

SOURCE_IDS: tuple[str, ...] = tuple(s.id for s in SOURCES)


def sources_by_id(ids: list[str] | None = None) -> list[NasaSource]:
    if ids is None:
        return list(SOURCES)
    wanted = set(ids)
    return [s for s in SOURCES if s.id in wanted]


@router.get("/daily/sources")
def list_sources() -> list[NasaSource]:
    return list(SOURCES)
