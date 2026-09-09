"""Reproducible popularity ranking with fair allocation inside cutoff ties."""

import hashlib
from collections import defaultdict

SELECTION_SEED = "scalaland-artifact-selection-v1"


def stable_hash(identity: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}:{identity}".encode()).hexdigest()


def rank_artifacts(memberships: dict[str, set[str]], counts: dict[str, int], cap: int) -> list[str]:
    groups: dict[int | None, list[str]] = defaultdict(list)
    for artifact in memberships:
        groups[counts.get(artifact)].append(artifact)
    result: list[str] = []
    for count in sorted(groups, key=lambda n: (n is None, -(n or 0))):
        group = sorted(groups[count], key=stable_hash)
        slots = cap - len(result)
        if 0 < slots < len(group):
            # One slot per artifact. A multi-cell artifact credits every membership;
            # it disappears from all queues as soon as it is selected.
            remaining = set(group)
            cells = {cell for a in group for cell in memberships[a]}
            credited = dict.fromkeys(cells, 0)
            chosen = []
            for _ in range(slots):
                available = {c for c in cells if any(c in memberships[a] for a in remaining)}
                cell = min(available, key=lambda c: (credited[c], stable_hash(c)))
                artifact = min((a for a in remaining if cell in memberships[a]), key=stable_hash)
                chosen.append(artifact)
                remaining.remove(artifact)
                for c in memberships[artifact]:
                    credited[c] += 1
            group = chosen + sorted(remaining, key=stable_hash)
        result.extend(group)
    return result
