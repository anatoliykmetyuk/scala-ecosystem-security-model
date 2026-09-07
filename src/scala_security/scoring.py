"""Provisional formulas with explicit coverage and human-readable inputs."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .data import JSON, number, obj, rows, string

SECURITY_WEIGHTS = {
    "Code-Review": 2,
    "Branch-Protection": 2,
    "Token-Permissions": 2,
    "Dangerous-Workflow": 3,
    "Pinned-Dependencies": 2,
    "Security-Policy": 1,
    "Vulnerabilities": 2,
    "SAST": 1,
}


def value(stars: float | None) -> float | None:
    return min(1.0, math.log1p(max(0, stars)) / math.log1p(100000)) if stars is not None else None


def age(date: object, now: datetime) -> int | None:
    try:
        parsed = datetime.fromisoformat(string(date).replace("Z", "+00:00"))
        return max(0, (now - parsed.replace(tzinfo=timezone.utc)).days)
    except ValueError:
        return None


@dataclass
class Part:
    name: str
    value: float
    weight: float


@dataclass
class Check:
    name: str
    score: float | None
    weight: int
    reason: str


@dataclass
class Health:
    maintenance: float | None
    security: float | None
    maintenance_coverage: float
    security_coverage: float
    push_days: int | None
    humans: int | None
    absence_factor: int | None
    archived: bool
    parts: list[Part]
    checks: list[Check]
    maintenance_note: str
    security_note: str
    scan_date: str

    def payload(self) -> dict[str, JSON]:
        return obj(asdict(self))


def health(
    repository: dict[str, JSON], commits: dict[str, JSON], scorecard: dict[str, JSON], now: datetime
) -> Health:
    push_days = age(repository.get("pushed_at"), now)
    repo_age = age(repository.get("last_synced_at"), now)
    commit_age = age(commits.get("last_synced_at"), now)
    scan_age = age(scorecard.get("date"), now)
    humans: int | None = None
    caf: int | None = None
    raw = commits.get("past_year_committers")
    if isinstance(raw, list):
        counts: list[float] = []
        for person in rows(raw):
            identity = " ".join(string(person.get(k)) for k in ("login", "name", "email")).lower()
            if any(
                tag in identity
                for tag in (
                    "[bot]",
                    "dependabot",
                    "renovate",
                    "scala-steward",
                    "scala steward",
                    "github-actions",
                )
            ):
                continue
            count = number(person.get("count"))
            if count is not None and count > 0:
                counts.append(count)
        counts.sort(reverse=True)
        humans, caf, accumulated = len(counts), 0, 0.0
        for count in counts:
            caf += 1
            accumulated += count
            if accumulated >= sum(counts) / 2:
                break
    parts: list[Part] = []
    if repo_age is not None and repo_age <= 90 and push_days is not None:
        parts.append(Part("Push recency", max(0, 1 - push_days / 365), 0.25))
    if commit_age is not None and commit_age <= 90 and humans is not None and caf is not None:
        parts.extend(
            [
                Part("Human author records", min(1, humans / 5), 0.35),
                Part("Contributor absence factor", min(1, caf / 3), 0.40),
            ]
        )
    coverage = sum(p.weight for p in parts)
    maintenance = sum(p.value * p.weight for p in parts) / coverage if coverage >= 0.65 else None
    archived = repository.get("archived") is True and repo_age is not None and repo_age <= 90
    if archived:
        maintenance = 0.0
    checks: list[Check] = []
    supplied = {string(c.get("name")): c for c in rows(scorecard.get("checks"))}
    for name, weight in SECURITY_WEIGHTS.items():
        check = supplied.get(name, {})
        score = number(check.get("score"))
        score = score if score is not None and 0 <= score <= 10 else None
        checks.append(
            Check(name, score, weight, string(check.get("reason")) or "No usable observation")
        )
    observed = sum(c.weight for c in checks if c.score is not None)
    security_coverage = observed / sum(SECURITY_WEIGHTS.values())
    security = (
        sum(c.score / 10 * c.weight for c in checks if c.score is not None) / observed
        if security_coverage >= 0.6 and scan_age is not None and scan_age <= 90
        else None
    )
    mn = (
        "Fresh archival evidence overrides the formula: M = 0."
        if archived
        else (
            "Insufficient fresh evidence: at least 65% of planned weight is required."
            if maintenance is None
            else "Available fresh inputs are weighted and renormalized by their observed weight."
        )
    )
    sn = (
        "At least 60% of planned check weight and a scan no older than 90 days are required."
        if security is None
        else "Unavailable checks are excluded; the remaining weights are renormalized."
    )
    return Health(
        maintenance,
        security,
        coverage,
        security_coverage,
        push_days,
        humans,
        caf,
        archived,
        parts,
        checks,
        mn,
        sn,
        string(scorecard.get("date")),
    )
