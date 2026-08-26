"""Context for a score, without turning it into a rank.

"Is 4.2 good?" has no answer on its own. The only comparison available without
context is against other people, which is the most damaging way to read this
data and the easiest one to reach for.

So this returns a band — the middle half of what comparable subjects scored —
and nothing else. No names, no ids, no position, no percentile. A percentile is
a ranking with one row visible, and a ranking is what gets used for decisions
this data cannot support.

Two things constrain it:

  - The comparison group is the same curriculum in the same term. The schema
    has no department or subject-type entity, so that is the honest grouping
    rather than the one the roadmap imagined.
  - The viewer's own assignment is excluded from the band, and there is a
    minimum cohort size. With two instructors in a department, a median tells
    the first exactly what the second scored.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import AcademicTerm
from app.services.reporting import assignment_reports

# Excluding the viewer's own. Below this the band is not published at all:
# a small cohort plus your own known value narrows what everyone else scored,
# which is the same disclosure problem the comment threshold guards against.
MIN_COHORT = 5


@dataclass
class Band:
    size: int
    p25: float
    median: float
    p75: float
    basis: str

    def as_dict(self) -> dict:
        return {
            "size": self.size,
            "p25": self.p25,
            "median": self.median,
            "p75": self.p75,
            "basis": self.basis,
        }


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    p25, median, p75 = statistics.quantiles(ordered, n=4, method="inclusive")
    return round(p25, 2), round(median, 2), round(p75, 2)


def bands_for(
    db: Session, term: AcademicTerm, reports: list[dict]
) -> dict[int, dict | None]:
    """assignment id -> the band it should be read against, or None.

    None means there is no honest comparison to draw: too few comparable
    subjects, or not enough of them with a published mean.
    """
    if not reports:
        return {}

    # Everything taught in this term, so the cohort can be built per curriculum.
    everything = assignment_reports(db, term)

    by_curriculum: dict[str, list[dict]] = {}
    for entry in everything:
        by_curriculum.setdefault(entry["curriculum"].strip().lower(), []).append(entry)

    result: dict[int, dict | None] = {}
    for report in reports:
        peers = by_curriculum.get(report["curriculum"].strip().lower(), [])

        # Only assignments with a published mean count. One drawn from three
        # responses is not a comparison point, and including it would let the
        # band be moved by a figure the system refuses to show.
        values = [
            entry["mean"]
            for entry in peers
            if entry["mean"] is not None
            and entry["assignment_id"] != report["assignment_id"]
        ]

        if len(values) < MIN_COHORT:
            result[report["assignment_id"]] = None
            continue

        p25, median, p75 = _quartiles(values)
        result[report["assignment_id"]] = Band(
            size=len(values),
            p25=p25,
            median=median,
            p75=p75,
            basis=(
                f"{len(values)} other subjects in {report['curriculum']}, "
                f"{term.year} semester {term.semester}"
            ),
        ).as_dict()

    return result
