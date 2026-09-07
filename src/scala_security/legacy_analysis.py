"""Transparent provisional scores and version-aware cohort exposure."""

from collections import deque
from datetime import datetime, timezone

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


def age(date, now):
    try:
        return max(
            0,
            (
                now
                - datetime.fromisoformat(date.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
            ).days,
        )
    except (ValueError, TypeError, AttributeError):
        return None


def bot(person):
    identity = " ".join(str(person.get(k) or "") for k in ("login", "name", "email")).lower()
    return "[bot]" in identity or any(
        x in identity
        for x in ("dependabot", "renovate", "scala-steward", "scala steward", "github-actions")
    )


def contributor_metrics(data):
    people = data.get("past_year_committers")
    if not isinstance(people, list):
        return None, None, None
    # Do not publish identities. Count observed author records, without inferring
    # employer, individual risk, or merging people by similar display names.
    counts = sorted(
        [p.get("count", 0) for p in people if not bot(p) and p.get("count", 0) > 0], reverse=True
    )
    total = sum(counts)
    if not total:
        return 0, 0, 0
    acc = 0
    for i, count in enumerate(counts, 1):
        acc += count
        if acc >= total / 2:
            return len(counts), i, total


def health(evidence, now):
    repo = evidence.get("repository") or {}
    commits = evidence.get("commits") or {}
    issues = evidence.get("issues") or {}
    sc = evidence.get("scorecard") or {}
    repo_age = age(repo.get("last_synced_at"), now)
    commits_age = age(commits.get("last_synced_at"), now)
    sc_age = age(sc.get("date"), now)
    push_age = age(repo.get("pushed_at"), now)
    humans, caf, count = contributor_metrics(commits)
    parts = {}
    if repo_age is not None and repo_age <= 90 and push_age is not None:
        parts["push_recency"] = (max(0, 1 - push_age / 365), 0.25)
    if commits_age is not None and commits_age <= 90 and humans is not None:
        parts["human_authors"] = (min(1, humans / 5), 0.35)
        parts["contributor_absence_factor"] = (min(1, caf / 3), 0.40)
    mcoverage = sum(w for v, w in parts.values())
    maintenance = sum(v * w for v, w in parts.values()) / mcoverage if mcoverage >= 0.65 else None
    if repo.get("archived") is True and repo_age is not None and repo_age <= 90:
        maintenance = 0  # explicit archival override, retained as evidence
    checks = [
        {k: c.get(k) for k in ("name", "score", "reason", "documentation", "details")}
        for c in sc.get("checks", [])
        if c.get("name") in SECURITY_WEIGHTS
    ]
    valid = [
        c for c in checks if isinstance(c.get("score"), (int, float)) and 0 <= c["score"] <= 10
    ]
    total_weight = sum(SECURITY_WEIGHTS.values())
    observed_weight = sum(SECURITY_WEIGHTS[c["name"]] for c in valid)
    coverage = observed_weight / total_weight
    security = (
        sum(c["score"] / 10 * SECURITY_WEIGHTS[c["name"]] for c in valid) / observed_weight
        if coverage >= 0.60 and sc_age is not None and sc_age <= 90
        else None
    )
    return {
        "maintenance": maintenance,
        "security": security,
        "maintenance_coverage": mcoverage,
        "security_coverage": coverage,
        "archived": repo.get("archived"),
        "push_age_days": push_age,
        "past_year_human_authors": humans,
        "past_year_human_commits": count,
        "contributor_absence_factor": caf,
        "maintenance_parts": parts,
        "repository_age_days": repo_age,
        "commits_age_days": commits_age,
        "scorecard_age_days": sc_age,
        "scorecard_date": sc.get("date"),
        "scorecard_commit": (sc.get("repo") or {}).get("commit"),
        "checks": checks,
        "past_year_prs": issues.get("past_year_pull_requests_count"),
        "past_year_bot_prs": issues.get("past_year_bot_pull_requests_count"),
        "past_year_mean_pr_close_days": (
            issues["past_year_avg_time_to_close_pull_request"] / 86400
            if issues.get("past_year_avg_time_to_close_pull_request") is not None
            else None
        ),
        "issues_last_synced_at": issues.get("last_synced_at"),
        "sources": evidence.get("sources", {}),
    }


def reach(root, adjacency, max_hops, tooling=False):
    """Walk exact version IDs. Optional edges never auto-propagate.

    Broader mode includes nonoptional test/provided/build dependencies only on
    the first step, and runtime/compile dependencies on later steps.
    """
    paths = {root: []}
    queue = deque([root])
    while queue:
        source = queue.popleft()
        depth = len(paths[source])
        if depth >= max_hops:
            continue
        for e in adjacency.get(source, []):
            allowed = e["kind"] in ("runtime", "compile") or (
                tooling and depth == 0 and e["kind"] in ("test", "development", "provided", "build")
            )
            if not allowed or e["optional"] is not False or not e["exact"]:
                continue
            if e["target"] not in paths:
                paths[e["target"]] = paths[source] + [e]
                queue.append(e["target"])
    paths.pop(root, None)
    return paths
